<template>
  <div class="simulation-view">
    <!-- Back link -->
    <div class="breadcrumb">
      <router-link to="/">← Today's Matches</router-link>
    </div>

    <!-- Disclaimer (redundant here as it's in DisclaimerBar — belt and braces) -->
    <div class="page-disclaimer">
      ⚠️ <strong>SIMULATION ONLY</strong> — Not betting advice. Not a guarantee of outcomes.
      For research and entertainment only.
    </div>

    <!-- Loading / running state -->
    <div v-if="isRunning" class="progress-section">
      <SimulationProgress
        :status="sessionStatus"
        :progress-pct="progressPct"
        :phase="currentPhase"
        :sims-complete="simsComplete"
        :sims-total="simsTotal"
        :events="wsEvents"
        :error-message="errorMessage"
      />
    </div>

    <!-- Error state -->
    <div v-else-if="sessionStatus === 'failed'" class="error-state card">
      <h2>Simulation Failed</h2>
      <p>{{ errorMessage || 'An unknown error occurred.' }}</p>
      <router-link to="/" class="btn btn-secondary">← Back to Matches</router-link>
    </div>

    <!-- Results state -->
    <div v-else-if="result" class="results-section">
      <div class="result-header">
        <h1 class="result-title">Simulation Complete</h1>
        <div class="result-meta">
          <span class="result-id">ID: {{ id }}</span>
          <span v-if="result.simulation_mode" class="mode-badge" :class="'mode-' + result.simulation_mode">
            {{ modeBadgeLabel }}
          </span>
        </div>
      </div>

      <!-- Report section -->
      <div class="report-section card" v-if="result.report">
        <h2 class="report-title">Prediction Report</h2>

        <!-- Win probability — D3 chart -->
        <div class="win-probability" v-if="result.report.win_probability">
          <WinProbabilityChart
            title="Win Probability (95% CI)"
            :win-probability="filteredWinProb"
            :predicted-winner="result.report.prediction?.winner"
          />
        </div>

        <!-- Score distribution — D3 histogram -->
        <div class="score-dist" v-if="result.report.score_distribution?.histogram_data">
          <ScoreDistributionChart
            title="Score Distribution"
            :histogram-data="result.report.score_distribution.histogram_data"
            :score-stats="result.report.score_distribution"
          />
        </div>

        <!-- Prediction summary -->
        <div class="prediction-box" v-if="result.report.prediction">
          <div class="prediction-winner">
            🏆 Predicted winner:
            <strong>{{ result.report.prediction.winner }}</strong>
          </div>
          <div class="prediction-confidence">
            Confidence:
            <span
              class="confidence-badge"
              :class="'confidence-' + result.report.prediction.confidence_label?.toLowerCase()"
            >{{ result.report.prediction.confidence_label }}</span>
            ({{ result.report.prediction.confidence_pct }}%)
          </div>
          <div class="prediction-summary" v-if="result.report.prediction.summary">
            {{ result.report.prediction.summary }}
          </div>
        </div>

        <!-- LLM narrative -->
        <div class="llm-narrative" v-if="result.report.llm_narrative">
          <h3 class="section-label">AI Analysis</h3>
          <div class="narrative-text">{{ result.report.llm_narrative }}</div>
        </div>

        <!-- Sim summary (multi-sim) -->
        <div class="sim-summary" v-if="result.summary?.total_simulations > 1">
          <h3 class="section-label">Simulation Summary</h3>
          <div class="summary-grid">
            <div class="summary-stat">
              <span class="stat-val">{{ result.summary.total_simulations }}</span>
              <span class="stat-label">Simulations</span>
            </div>
            <div
              v-for="(pct, team) in result.summary.win_percentages"
              :key="team"
              class="summary-stat"
            >
              <span class="stat-val">{{ pct }}%</span>
              <span class="stat-label">{{ team }} wins</span>
            </div>
          </div>
        </div>

        <!-- Key moments -->
        <div class="key-moments" v-if="result.match_result?.key_moments?.length">
          <h3 class="km-title">Key Moments</h3>
          <ul class="km-list">
            <li v-for="(moment, i) in result.match_result.key_moments" :key="i">
              {{ moment }}
            </li>
          </ul>
        </div>

        <!-- Caveats -->
        <div class="caveats" v-if="result.report.caveats?.length">
          <div v-for="(c, i) in result.report.caveats" :key="i" class="caveat-item">
            ℹ️ {{ c }}
          </div>
        </div>
      </div>

      <!-- Footer disclaimer (redundant — belt and braces) -->
      <div class="result-disclaimer">
        {{ disclaimer }}
      </div>

      <!-- Action buttons -->
      <div class="result-actions">
        <router-link to="/" class="btn btn-secondary">← Simulate Another Match</router-link>
      </div>
    </div>

    <!-- Pending/not found state -->
    <div v-else class="pending-state card">
      <span class="loading-spinner"></span>
      <p>Loading simulation {{ id }}...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import axios from 'axios'
import SimulationProgress from '../components/SimulationProgress.vue'
import ScoreDistributionChart from '../components/ScoreDistributionChart.vue'
import WinProbabilityChart from '../components/WinProbabilityChart.vue'
import { useSimulationStore } from '../stores/simulation.js'

const simStore = useSimulationStore()

const props = defineProps({
  id: {
    type: String,
    required: true,
  },
})

// State
const sessionStatus = ref('pending')
const progressPct = ref(0)
const currentPhase = ref('initializing')
const simsComplete = ref(0)
const simsTotal = ref(100)
const errorMessage = ref('')
const result = ref(null)
const wsEvents = ref([])
const disclaimer = ref('')

let pollInterval = null
let ws = null

const isRunning = computed(() =>
  ['pending', 'running'].includes(sessionStatus.value)
)

const modeBadgeLabel = computed(() => {
  const m = result.value?.simulation_mode
  if (m === 'persona') return 'Persona Mode (Full LLM)'
  if (m === 'hybrid') return 'Hybrid Mode (Smart LLM)'
  if (m === 'probabilistic') return 'Probabilistic (No LLM)'
  return m || ''
})

const hasPhaseScoring = computed(() => {
  return result.value?.innings?.innings1?.phase_scoring || result.value?.innings?.innings2?.phase_scoring
})

const filteredWinProb = computed(() => {
  if (!result.value?.report?.win_probability) return {}
  const wp = result.value.report.win_probability
  // Filter out 'no_result' key
  return Object.fromEntries(
    Object.entries(wp).filter(([k]) => k !== 'no_result' && typeof wp[k] === 'object')
  )
})

function isWinner(team, report) {
  return report?.prediction?.winner === team
}

function formatPlayerName(rawName) {
  // Convert "MI_Opener1" → "Opener 1"
  if (!rawName) return ''
  const parts = rawName.split('_')
  if (parts.length >= 2) {
    return parts.slice(1).join(' ').replace(/([a-z])([A-Z])/g, '$1 $2')
  }
  return rawName
}

onMounted(() => {
  startPolling()
  connectWebSocket()
})

onUnmounted(() => {
  stopPolling()
  disconnectWebSocket()
})

function startPolling() {
  pollInterval = setInterval(async () => {
    try {
      const resp = await axios.get(`/api/simulation/${props.id}/status`)
      const data = resp.data
      sessionStatus.value = data.status
      progressPct.value = data.progress_pct || 0
      currentPhase.value = data.phase || 'running'
      simsComplete.value = data.sims_complete || 0
      simsTotal.value = data.sims_total || 1
      errorMessage.value = data.error || ''

      if (data.status === 'completed') {
        stopPolling()
        simStore.finish()
        await loadResult()
      } else if (data.status === 'failed') {
        stopPolling()
        simStore.finish()
        errorMessage.value = data.error || 'Simulation failed'
      }
    } catch (e) {
      // Ignore polling errors
    }
  }, 1000)
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

async function loadResult() {
  try {
    const resp = await axios.get(`/api/simulation/${props.id}/result`)
    result.value = resp.data
    disclaimer.value = resp.data.disclaimer || ''
  } catch (e) {
    errorMessage.value = 'Failed to load result'
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/simulation/${props.id}/stream`

  try {
    ws = new WebSocket(wsUrl)

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        wsEvents.value.push({
          ...data,
          timestamp: new Date().toISOString(),
        })
        // Keep only last 50 events
        if (wsEvents.value.length > 50) {
          wsEvents.value = wsEvents.value.slice(-50)
        }
      } catch {
        // Ignore malformed events
      }
    }

    ws.onerror = () => {
      // WebSocket failed — polling will handle state updates
    }
  } catch {
    // WebSocket not available — polling handles everything
  }
}

function disconnectWebSocket() {
  if (ws) {
    ws.close()
    ws = null
  }
}
</script>

<style scoped>
.simulation-view {
  max-width: 960px;
  margin: 0 auto;
}

.breadcrumb {
  margin-bottom: 1rem;
  font-size: 0.85rem;
}

.page-disclaimer {
  background: #1a0a00;
  border: 1px solid #ff9800;
  border-radius: var(--border-radius);
  padding: 0.6rem 1rem;
  font-size: 0.8rem;
  color: #ffcc80;
  margin-bottom: 1.5rem;
}

.page-disclaimer strong {
  color: #ff9800;
}

.progress-section {
  margin-bottom: 2rem;
}

/* Scoreboard */
.scoreboard {
  margin-bottom: 1.5rem;
}

.scoreboard-title {
  font-size: 1.2rem;
  font-weight: 700;
  margin-bottom: 1rem;
}

.toss-info {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin-bottom: 1rem;
  padding: 0.5rem 0.75rem;
  background: var(--color-surface-2);
  border-radius: var(--border-radius);
}

.innings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

@media (max-width: 640px) {
  .innings-grid {
    grid-template-columns: 1fr;
  }
}

.innings-block {
  background: var(--color-surface-2);
  border-radius: var(--border-radius);
  padding: 1rem;
}

.innings-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.innings-team {
  font-size: 1rem;
  font-weight: 700;
}

.innings-score {
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--color-primary);
}

.innings-overs {
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

.innings-meta {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin-bottom: 1rem;
}

.bowling-figures {
  margin-top: 0.75rem;
}

.figures-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.4rem;
}

.bowler-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  padding: 0.15rem 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}

.bowler-name {
  color: var(--color-text);
}

.bowler-fig {
  color: var(--color-text-muted);
}

.fow-section {
  margin-top: 0.75rem;
}

.fow-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.fow-item {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  background: var(--color-surface);
  padding: 2px 6px;
  border-radius: 4px;
}

.winner-banner {
  margin-top: 1.5rem;
  padding: 1rem 1.5rem;
  background: linear-gradient(135deg, rgba(108, 99, 255, 0.2), rgba(255, 101, 132, 0.2));
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius);
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.winner-label {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}

.winner-name {
  font-size: 1.3rem;
  font-weight: 800;
  color: var(--color-primary);
}

.winner-margin {
  font-size: 0.9rem;
  color: var(--color-text-muted);
}

/* Phase Scoring */
.phase-scoring {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
}

.phase-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}

.phase-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 640px) {
  .phase-grid {
    grid-template-columns: 1fr;
  }
}

.phase-team-name {
  font-size: 0.85rem;
  font-weight: 700;
  margin-bottom: 0.4rem;
  color: var(--color-primary);
}

.phase-rows {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.phase-row {
  display: grid;
  grid-template-columns: 80px 40px 50px 55px 55px;
  align-items: center;
  font-size: 0.75rem;
  color: var(--color-text);
  padding: 3px 6px;
  background: var(--color-surface);
  border-radius: 4px;
}

.phase-label {
  font-weight: 600;
  color: var(--color-text-muted);
}

.phase-overs {
  color: var(--color-text-muted);
  font-size: 0.7rem;
}

.phase-runs {
  font-weight: 700;
}

.phase-rr {
  color: var(--color-text-muted);
  font-size: 0.7rem;
}

.phase-bounds {
  color: var(--color-text-muted);
  font-size: 0.7rem;
}

/* Winning Factors */
.winning-factors {
  margin-bottom: 1.5rem;
}

.wf-title {
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 1rem;
  color: var(--color-success);
}

.wf-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.wf-item {
  padding: 0.75rem 1rem;
  border-radius: var(--border-radius);
  border-left: 3px solid;
}

.wf-high {
  background: rgba(76, 175, 80, 0.08);
  border-left-color: var(--color-success);
}

.wf-medium {
  background: rgba(255, 152, 0, 0.08);
  border-left-color: var(--color-warning);
}

.wf-low {
  background: rgba(108, 99, 255, 0.08);
  border-left-color: var(--color-primary);
}

.wf-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.3rem;
}

.wf-impact-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.wf-high .wf-impact-dot { background: var(--color-success); }
.wf-medium .wf-impact-dot { background: var(--color-warning); }
.wf-low .wf-impact-dot { background: var(--color-primary); }

.wf-factor-name {
  font-weight: 700;
  font-size: 0.9rem;
}

.wf-impact-badge {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: 10px;
  margin-left: auto;
}

.wf-high .wf-impact-badge {
  background: rgba(76, 175, 80, 0.2);
  color: var(--color-success);
}

.wf-medium .wf-impact-badge {
  background: rgba(255, 152, 0, 0.2);
  color: var(--color-warning);
}

.wf-low .wf-impact-badge {
  background: rgba(108, 99, 255, 0.2);
  color: var(--color-primary);
}

.wf-detail {
  font-size: 0.85rem;
  color: var(--color-text);
  line-height: 1.5;
  margin: 0;
}

/* Report */
.report-section {
  margin-bottom: 1.5rem;
}

.report-title {
  font-size: 1.2rem;
  font-weight: 700;
  margin-bottom: 1.5rem;
}

.win-probability {
  margin-bottom: 1.5rem;
}

.wp-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 1rem;
}

.wp-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.wp-team {
  display: grid;
  grid-template-columns: 80px 1fr 60px;
  align-items: center;
  gap: 0.75rem;
}

.wp-team-name {
  font-weight: 600;
  font-size: 0.9rem;
}

.wp-bar-wrap {
  height: 8px;
  background: var(--color-surface-2);
  border-radius: 4px;
  overflow: hidden;
}

.wp-bar {
  height: 100%;
  background: var(--color-primary);
  border-radius: 4px;
  transition: width 1s ease;
}

.wp-bar.wp-bar-winner {
  background: var(--color-success);
}

.wp-pct {
  font-size: 0.9rem;
  font-weight: 700;
  text-align: right;
}

.wp-ci {
  grid-column: 2 / 4;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.prediction-box {
  background: var(--color-surface-2);
  border-radius: var(--border-radius);
  padding: 1rem;
  margin-bottom: 1.5rem;
}

.prediction-winner {
  font-size: 1rem;
  margin-bottom: 0.5rem;
}

.prediction-winner strong {
  color: var(--color-success);
  font-size: 1.1rem;
}

.prediction-confidence {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.confidence-badge {
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 700;
}

.confidence-high {
  background: rgba(76, 175, 80, 0.2);
  color: var(--color-success);
  border: 1px solid var(--color-success);
}

.confidence-medium {
  background: rgba(255, 152, 0, 0.2);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
}

.confidence-low {
  background: rgba(244, 67, 54, 0.2);
  color: var(--color-danger);
  border: 1px solid var(--color-danger);
}

.prediction-summary {
  font-size: 0.85rem;
  color: var(--color-text);
  line-height: 1.5;
}

.score-dist {
  margin-bottom: 1.5rem;
}

.section-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}

.llm-narrative {
  margin-bottom: 1.5rem;
}

.narrative-text {
  font-size: 0.9rem;
  line-height: 1.7;
  color: var(--color-text);
  white-space: pre-line;
}

.sim-summary {
  margin-bottom: 1.5rem;
}

.summary-grid {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.summary-stat {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.stat-val {
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--color-primary);
}

.stat-label {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.km-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}

.km-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.km-list li {
  font-size: 0.85rem;
  padding-left: 1rem;
  position: relative;
}

.km-list li::before {
  content: '→';
  position: absolute;
  left: 0;
  color: var(--color-primary);
}

.caveats {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.caveat-item {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.result-disclaimer {
  background: #1a0a00;
  border: 1px solid #ff9800;
  border-radius: var(--border-radius);
  padding: 0.75rem 1rem;
  font-size: 0.78rem;
  color: #ffcc80;
  margin: 1.5rem 0;
  line-height: 1.5;
}

.result-actions {
  margin-bottom: 2rem;
  display: flex;
  gap: 1rem;
}

.result-header {
  margin-bottom: 1.5rem;
}

.result-title {
  font-size: 1.8rem;
  font-weight: 800;
  margin-bottom: 0.25rem;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.result-id {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  font-family: monospace;
}

.mode-badge {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 20px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.mode-persona {
  background: rgba(255, 101, 132, 0.15);
  color: #ff6584;
  border: 1px solid #ff6584;
}

.mode-hybrid {
  background: rgba(108, 99, 255, 0.15);
  color: #6c63ff;
  border: 1px solid #6c63ff;
}

.mode-probabilistic {
  background: rgba(76, 175, 80, 0.15);
  color: #4caf50;
  border: 1px solid #4caf50;
}

.pending-state {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 2rem;
  color: var(--color-text-muted);
}

.error-state {
  padding: 2rem;
  text-align: center;
}

.error-state h2 {
  color: var(--color-danger);
  margin-bottom: 1rem;
}

.error-state p {
  color: var(--color-text-muted);
  margin-bottom: 1.5rem;
}
</style>
