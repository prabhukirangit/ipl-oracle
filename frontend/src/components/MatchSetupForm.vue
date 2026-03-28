<template>
  <div class="match-setup-form card">
    <h2 class="form-title">Configure Simulation</h2>
    <p class="form-subtitle">
      Select a match and configure the simulation parameters.
    </p>

    <form @submit.prevent="handleSubmit" class="form-body">
      <!-- Match Info (pre-filled from parent) -->
      <div class="form-section">
        <h3 class="section-title">Match Details</h3>
        <div class="match-info-display">
          <div class="match-teams">
            <span class="team-name team1">{{ match.team1 }}</span>
            <span class="vs-label">vs</span>
            <span class="team-name team2">{{ match.team2 }}</span>
          </div>
          <div class="match-meta">
            <span>{{ match.venue }}</span>
            <span>{{ match.match_date_display }}</span>
            <span>{{ match.match_time_display }}</span>
          </div>
          <!-- Match state badge -->
          <div class="match-state-info">
            <span
              class="badge"
              :class="{
                'badge-live': match.match_status === 'LIVE',
                'badge-future': match.match_status === 'FUTURE',
                'badge-imminent': match.match_status === 'IMMINENT',
              }"
            >{{ match.match_status }}</span>
            <span v-if="match.state_details?.caveats?.length" class="caveat-text">
              {{ match.state_details.caveats[0] }}
            </span>
          </div>
        </div>
      </div>

      <!-- Pitch Type -->
      <div class="form-section">
        <h3 class="section-title">Pitch Conditions</h3>
        <div class="form-group">
          <label class="form-label" for="pitch-type">Pitch Type</label>
          <select
            id="pitch-type"
            v-model="formData.pitchType"
            class="form-select"
          >
            <option value="balanced">Balanced (Default)</option>
            <option value="batting_friendly">Batting Friendly</option>
            <option value="batting_paradise">Batting Paradise</option>
            <option value="spin_friendly">Spin Friendly</option>
            <option value="pace_friendly">Pace Friendly</option>
          </select>
          <p class="form-hint">
            Pitch type affects scoring rates and bowler effectiveness over time.
          </p>
        </div>
      </div>

      <!-- Simulation Parameters -->
      <div class="form-section">
        <h3 class="section-title">Simulation Parameters</h3>

        <!-- Simulation Mode -->
        <div class="form-group">
          <label class="form-label" for="sim-mode">
            Mode
            <span class="form-badge">{{ modeBadge }}</span>
          </label>
          <select
            id="sim-mode"
            v-model="formData.simulationMode"
            class="form-input"
          >
            <option value="persona">Persona — LLM plays as real cricketers</option>
            <option value="hybrid">Hybrid — LLM at key moments only</option>
            <option value="probabilistic">Fast — pure probability engine</option>
          </select>
          <p class="form-hint">
            {{ modeHint }}
          </p>
        </div>

        <!-- Simulation Count -->
        <div class="form-group">
          <label class="form-label" for="sim-count">
            Simulations
            <span class="form-badge">1–500 parallel runs</span>
          </label>
          <input
            id="sim-count"
            type="number"
            v-model.number="formData.simCount"
            min="1"
            :max="simCountMax"
            class="form-input"
          />
          <p class="form-hint">
            {{ simCountHint }}
          </p>
        </div>
      </div>

      <!-- Toss (optional) -->
      <div class="form-section">
        <h3 class="section-title">Toss (Optional)</h3>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label" for="toss-winner">Toss Winner</label>
            <select
              id="toss-winner"
              v-model="formData.tossWinner"
              class="form-select"
            >
              <option value="">Auto-simulate toss</option>
              <option :value="match.team1">{{ match.team1 }}</option>
              <option :value="match.team2">{{ match.team2 }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label" for="toss-decision">Decision</label>
            <select
              id="toss-decision"
              v-model="formData.tossDecision"
              class="form-select"
              :disabled="!formData.tossWinner"
            >
              <option value="">Auto-decide</option>
              <option value="bat">Bat First</option>
              <option value="field">Field First</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Submit -->
      <div class="form-actions">
        <button
          type="submit"
          class="btn btn-primary btn-large"
          :disabled="isSubmitting"
        >
          <span v-if="isSubmitting" class="loading-spinner"></span>
          <span v-else>🚀 Run Simulation</span>
        </button>
        <p class="submit-disclaimer">
          ⚠️ Results are for entertainment only. Not betting advice.
        </p>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'

const props = defineProps({
  match: {
    type: Object,
    required: true,
  },
  isSubmitting: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['submit'])

const formData = reactive({
  pitchType: 'balanced',
  simCount: 100,
  simulationMode: 'hybrid',
  tossWinner: '',
  tossDecision: '',
})

const modeBadge = computed(() => {
  const badges = {
    persona: 'Full LLM',
    hybrid: 'Smart LLM',
    probabilistic: 'No LLM',
  }
  return badges[formData.simulationMode] || 'Smart LLM'
})

const modeHint = computed(() => {
  const hints = {
    persona: 'Each player is an LLM persona making decisions in character. Team communication enabled. Best with 1-10 sims.',
    hybrid: 'LLM fires at high-leverage moments (last overs, wickets under pressure). Good balance of speed and intelligence.',
    probabilistic: 'Pure probability engine. No LLM calls. Fastest mode — ideal for large sim counts.',
  }
  return hints[formData.simulationMode] || hints.hybrid
})

const simCountMax = computed(() => {
  const limits = { persona: 10, hybrid: 100, probabilistic: 500 }
  return limits[formData.simulationMode] || 500
})

const simCountHint = computed(() => {
  if (formData.simulationMode === 'persona') {
    return 'Persona mode: max 10 sims. Each sim has full LLM impersonation per ball.'
  }
  if (formData.simulationMode === 'probabilistic') {
    return 'Fast mode: up to 500 sims. Pure probability — no LLM cost.'
  }
  return 'More simulations = higher confidence intervals. 50-100 recommended.'
})

function handleSubmit() {
  emit('submit', {
    matchId: props.match.match_id,
    team1: props.match.team1,
    team2: props.match.team2,
    venue: props.match.venue,
    matchStartTime: props.match.match_start_time,
    pitchType: formData.pitchType,
    simCount: Math.min(formData.simCount, simCountMax.value),
    simulationMode: formData.simulationMode,
    tossWinner: formData.tossWinner || null,
    tossDecision: formData.tossDecision || null,
  })
}
</script>

<style scoped>
.match-setup-form {
  max-width: 640px;
}

.form-title {
  font-size: 1.4rem;
  font-weight: 700;
  margin-bottom: 0.25rem;
}

.form-subtitle {
  color: var(--color-text-muted);
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
}

.form-section {
  margin-bottom: 1.5rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid var(--color-border);
}

.form-section:last-of-type {
  border-bottom: none;
}

.section-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 1rem;
}

.match-info-display {
  background: var(--color-surface-2);
  border-radius: var(--border-radius);
  padding: 1rem;
}

.match-teams {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.team-name {
  font-size: 1.3rem;
  font-weight: 700;
}

.team1 { color: var(--color-primary); }
.team2 { color: var(--color-accent); }

.vs-label {
  color: var(--color-text-muted);
  font-size: 0.9rem;
}

.match-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.85rem;
  color: var(--color-text-muted);
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}

.match-state-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.caveat-text {
  font-size: 0.8rem;
  color: var(--color-warning);
}

.form-group {
  margin-bottom: 1rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--color-text-muted);
  margin-bottom: 0.4rem;
}

.form-badge {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  padding: 1px 6px;
  font-size: 0.7rem;
  color: var(--color-text-muted);
  font-weight: normal;
}

.form-input,
.form-select {
  width: 100%;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius);
  color: var(--color-text);
  padding: 0.5rem 0.75rem;
  font-size: 0.9rem;
  font-family: var(--font-family);
  transition: var(--transition);
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-input:disabled,
.form-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.form-hint {
  font-size: 0.78rem;
  color: var(--color-text-muted);
  margin-top: 0.3rem;
}

.form-actions {
  margin-top: 1.5rem;
}

.btn-large {
  width: 100%;
  padding: 0.8rem 1.5rem;
  font-size: 1rem;
}

.submit-disclaimer {
  text-align: center;
  font-size: 0.75rem;
  color: var(--color-warning);
  margin-top: 0.75rem;
}
</style>
