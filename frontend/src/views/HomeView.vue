<template>
  <div class="home-view">
    <!-- Active simulation banner -->
    <div class="active-sim-banner" v-if="simStore.isRunning">
      <span class="banner-dot"></span>
      Simulation running: {{ simStore.activeTeams?.team1 }} vs {{ simStore.activeTeams?.team2 }}
      <router-link :to="{ name: 'simulation', params: { id: simStore.activeSimId } }" class="banner-link">
        View progress →
      </router-link>
    </div>

    <!-- Hero -->
    <section class="hero">
      <h1 class="hero-title">IPL Oracle</h1>
      <p class="hero-subtitle">
        AI-powered swarm intelligence engine for IPL match prediction.
        Spawns 60+ autonomous agents — players, coaches, stadium, pitch, weather, umpires —
        and runs parallel simulations across three engine modes to surface emergent win predictions.
      </p>
      <div class="hero-tags">
        <span class="tag">Persona Engine</span>
        <span class="tag">Hybrid Engine</span>
        <span class="tag">Probabilistic Engine</span>
        <span class="tag">Not Betting Advice</span>
      </div>
    </section>

    <!-- Today's matches -->
    <section class="schedule-section">
      <div class="section-header">
        <h2 class="section-title">Today's Matches</h2>
        <span class="section-date">{{ todayDisplay }}</span>
      </div>

      <!-- Loading state -->
      <div v-if="loading" class="loading-state">
        <span class="loading-spinner"></span>
        <span>Loading schedule...</span>
      </div>

      <!-- Error state -->
      <div v-else-if="error" class="error-state card">
        <p>⚠️ Could not load schedule: {{ error }}</p>
        <p class="error-hint">Make sure the backend is running on port 8000.</p>
        <button @click="loadSchedule" class="btn btn-secondary">Retry</button>
      </div>

      <!-- No matches today -->
      <div v-else-if="todayMatches.length === 0" class="no-matches card">
        <p>No matches scheduled today.</p>
        <p class="no-matches-hint">
          Check the upcoming matches below, or come back on a match day.
        </p>
      </div>

      <!-- Match cards -->
      <div v-else class="matches-grid">
        <MatchCard
          v-for="match in todayMatches"
          :key="match.match_id"
          :match="match"
          @simulate="handleSimulate"
        />
      </div>
    </section>

    <!-- Upcoming matches -->
    <section class="schedule-section" v-if="upcomingMatches.length">
      <div class="section-header">
        <h2 class="section-title">Upcoming (Next 7 Days)</h2>
      </div>
      <div class="matches-grid">
        <MatchCard
          v-for="match in upcomingMatches"
          :key="match.match_id"
          :match="match"
          @simulate="handleSimulate"
          compact
        />
      </div>
    </section>

    <!-- Match setup form modal -->
    <div v-if="selectedMatch" class="modal-overlay" @click.self="closeModal">
      <div class="modal-content">
        <button class="modal-close" @click="closeModal">✕</button>
        <MatchSetupForm
          :match="selectedMatch"
          :is-submitting="isSubmitting"
          @submit="startSimulation"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import MatchSetupForm from '../components/MatchSetupForm.vue'
import MatchCard from '../components/MatchCard.vue'
import { useSimulationStore } from '../stores/simulation.js'

const router = useRouter()
const simStore = useSimulationStore()

// State
const loading = ref(true)
const error = ref(null)
const todayMatches = ref([])
const upcomingMatches = ref([])
const selectedMatch = ref(null)
const isSubmitting = ref(false)

const todayDisplay = computed(() => {
  return new Date().toLocaleDateString('en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
})

// Load schedule on mount
onMounted(() => {
  loadSchedule()
})

async function loadSchedule() {
  loading.value = true
  error.value = null
  try {
    const [todayResp, upcomingResp] = await Promise.all([
      axios.get('/api/schedule/today'),
      axios.get('/api/schedule/upcoming?days=7'),
    ])
    todayMatches.value = todayResp.data.matches || []
    // Upcoming = exclude today
    const todayIds = new Set(todayMatches.value.map(m => m.match_id))
    upcomingMatches.value = (upcomingResp.data.matches || []).filter(
      m => !todayIds.has(m.match_id)
    )
  } catch (e) {
    error.value = e.message || 'Network error'
    // Show demo data if backend is not running
    todayMatches.value = getDemoMatches()
  } finally {
    loading.value = false
  }
}

function handleSimulate(match) {
  if (!match.is_simulatable) return
  if (simStore.isRunning) {
    alert(`A simulation is already running (${simStore.activeTeams?.team1} vs ${simStore.activeTeams?.team2}). Wait for it to complete or view its progress.`)
    return
  }
  selectedMatch.value = match
}

function closeModal() {
  selectedMatch.value = null
}

async function startSimulation(formData) {
  isSubmitting.value = true
  try {
    const response = await axios.post('/api/simulation/start', {
      match_id: formData.matchId,
      team1: formData.team1,
      team2: formData.team2,
      venue: formData.venue,
      match_start_time: formData.matchStartTime,
      pitch_type: formData.pitchType,
      sim_count: formData.simCount,
      simulation_mode: formData.simulationMode || 'hybrid',
      toss_winner: formData.tossWinner || null,
      toss_decision: formData.tossDecision || null,
      team1_players: [],
      team2_players: [],
    })
    const simId = response.data.simulation_id
    simStore.start(simId, formData.team1, formData.team2)
    closeModal()
    router.push({ name: 'simulation', params: { id: simId } })
  } catch (e) {
    if (e.response?.status === 400) {
      alert('Cannot simulate this match: ' + (e.response.data?.detail?.message || 'Match may be completed.'))
    } else {
      alert('Failed to start simulation. Is the backend running?')
    }
  } finally {
    isSubmitting.value = false
  }
}

function getDemoMatches() {
  // Demo data for when backend is not running
  return [
    {
      match_id: 'DEMO_001',
      team1: 'RCB',
      team2: 'CSK',
      venue: 'M. Chinnaswamy Stadium, Bengaluru',
      city: 'Bengaluru',
      match_start_time: new Date().toISOString(),
      match_date: new Date().toISOString().split('T')[0],
      match_date_display: 'Today',
      match_time_display: '7:30 PM IST',
      match_status: 'FUTURE',
      is_simulatable: true,
      state_details: { caveats: ['Demo mode — backend not running'] },
    },
  ]
}
</script>

<style scoped>
.home-view {
  padding-top: 1rem;
}

.hero {
  text-align: center;
  padding: 2rem 0 3rem;
}

.hero-title {
  font-size: 3rem;
  font-weight: 900;
  background: linear-gradient(135deg, #6c63ff, #ff6584);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 0.75rem;
}

.hero-subtitle {
  max-width: 640px;
  margin: 0 auto 1.5rem;
  color: var(--color-text-muted);
  font-size: 1rem;
  line-height: 1.7;
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
}

.tag {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  padding: 4px 12px;
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.schedule-section {
  margin-bottom: 3rem;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.section-title {
  font-size: 1.3rem;
  font-weight: 700;
}

.section-date {
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--color-text-muted);
}

.error-state {
  color: var(--color-danger);
}

.error-hint {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin: 0.5rem 0 1rem;
}

.no-matches {
  text-align: center;
  padding: 2rem;
  color: var(--color-text-muted);
}

.no-matches-hint {
  margin-top: 0.5rem;
  font-size: 0.85rem;
}

.matches-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  z-index: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.modal-content {
  position: relative;
  max-width: 680px;
  width: 100%;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  width: 32px;
  height: 32px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 0.9rem;
  z-index: 10;
  transition: var(--transition);
}

.modal-close:hover {
  background: var(--color-border);
}

.active-sim-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: rgba(108, 99, 255, 0.12);
  border: 1px solid var(--color-primary);
  border-radius: var(--border-radius);
  padding: 0.6rem 1rem;
  font-size: 0.85rem;
  color: var(--color-primary);
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
}

.banner-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: pulse 1.5s infinite;
  flex-shrink: 0;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.banner-link {
  color: var(--color-primary);
  font-weight: 600;
  margin-left: auto;
}
</style>
