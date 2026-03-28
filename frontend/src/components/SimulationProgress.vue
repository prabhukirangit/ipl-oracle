<template>
  <div class="simulation-progress card">
    <div class="progress-header">
      <h3 class="progress-title">
        <span class="loading-spinner" v-if="status === 'running'"></span>
        {{ titleText }}
      </h3>
      <span class="progress-pct">{{ progressPct }}%</span>
    </div>

    <!-- Progress bar -->
    <div class="progress-bar-track">
      <div
        class="progress-bar-fill"
        :style="{ width: progressPct + '%' }"
        :class="{ 'progress-complete': status === 'completed' }"
      ></div>
    </div>

    <!-- Phase info -->
    <div class="phase-info">
      <span class="phase-label">Phase:</span>
      <span class="phase-value">{{ phaseDisplay }}</span>
    </div>

    <!-- Sims progress -->
    <div class="sims-counter" v-if="simsTotal > 1">
      {{ simsComplete }} / {{ simsTotal }} simulations complete
    </div>

    <!-- Live events from WebSocket -->
    <div class="live-events" v-if="events.length">
      <div class="events-title">Live Events</div>
      <div class="events-list">
        <div
          v-for="(event, i) in recentEvents"
          :key="i"
          class="event-item"
          :class="'event-' + (event.type || 'info')"
        >
          <span class="event-time">{{ formatTime(event.timestamp) }}</span>
          <span class="event-msg">{{ event.message || event.type }}</span>
        </div>
      </div>
    </div>

    <!-- Error state -->
    <div class="error-state" v-if="status === 'failed'">
      <p class="error-msg">⚠️ Simulation failed: {{ errorMessage }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: {
    type: String,
    default: 'pending',
  },
  progressPct: {
    type: Number,
    default: 0,
  },
  phase: {
    type: String,
    default: 'initializing',
  },
  simsComplete: {
    type: Number,
    default: 0,
  },
  simsTotal: {
    type: Number,
    default: 1,
  },
  events: {
    type: Array,
    default: () => [],
  },
  errorMessage: {
    type: String,
    default: '',
  },
})

const titleText = computed(() => {
  switch (props.status) {
    case 'pending': return 'Preparing simulation...'
    case 'running': return 'Simulation running...'
    case 'completed': return 'Simulation complete!'
    case 'failed': return 'Simulation failed'
    default: return 'Simulation in progress'
  }
})

const phaseDisplay = computed(() => {
  const phases = {
    initializing: 'Initializing',
    spawning_agents: 'Spawning agents (players, stadium, pitch, weather...)',
    simulating: 'Running match simulation ball-by-ball',
    generating_report: 'Generating prediction report',
  }
  return phases[props.phase] || props.phase
})

const recentEvents = computed(() => {
  return [...props.events].reverse().slice(0, 10)
})

function formatTime(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString()
  } catch {
    return ''
  }
}
</script>

<style scoped>
.simulation-progress {
  padding: 1.5rem;
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.progress-title {
  font-size: 1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.progress-pct {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--color-primary);
}

.progress-bar-track {
  height: 8px;
  background: var(--color-surface-2);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.75rem;
}

.progress-bar-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-bar-fill.progress-complete {
  background: var(--color-success);
}

.phase-info {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin-bottom: 0.5rem;
}

.phase-label {
  font-weight: 600;
  margin-right: 0.3rem;
}

.phase-value {
  color: var(--color-text);
}

.sims-counter {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin-bottom: 1rem;
}

.live-events {
  margin-top: 1rem;
  border-top: 1px solid var(--color-border);
  padding-top: 1rem;
}

.events-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  max-height: 160px;
  overflow-y: auto;
}

.event-item {
  display: flex;
  gap: 0.5rem;
  font-size: 0.8rem;
  padding: 0.2rem 0;
}

.event-time {
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.event-msg {
  color: var(--color-text);
}

.event-simulation_complete .event-msg {
  color: var(--color-success);
  font-weight: 600;
}

.event-error .event-msg {
  color: var(--color-danger);
}

.error-state {
  margin-top: 1rem;
  padding: 0.75rem;
  background: rgba(244, 67, 54, 0.1);
  border: 1px solid var(--color-danger);
  border-radius: var(--border-radius);
}

.error-msg {
  font-size: 0.85rem;
  color: var(--color-danger);
}
</style>
