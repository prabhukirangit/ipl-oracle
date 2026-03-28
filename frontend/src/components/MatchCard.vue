<template>
  <div class="match-card card" :class="{ 'match-card-compact': compact }">
    <div class="match-card-header">
      <div class="match-teams-row">
        <span class="mc-team1">{{ match.team1 }}</span>
        <span class="mc-vs">vs</span>
        <span class="mc-team2">{{ match.team2 }}</span>
      </div>
      <span
        class="badge"
        :class="{
          'badge-live': match.match_status === 'LIVE',
          'badge-future': match.match_status === 'FUTURE',
          'badge-imminent': match.match_status === 'IMMINENT',
        }"
      >{{ match.match_status }}</span>
    </div>

    <div class="match-card-body">
      <p class="mc-venue">🏟 {{ match.venue }}</p>
      <p class="mc-time">🕐 {{ match.match_time_display || '7:30 PM IST' }}</p>
      <p v-if="match.city" class="mc-city">📍 {{ match.city }}</p>
      <p
        v-if="match.state_details?.caveats?.length"
        class="mc-caveat"
      >
        {{ match.state_details.caveats[0] }}
      </p>
    </div>

    <div class="match-card-footer">
      <button
        class="btn"
        :class="match.is_simulatable ? 'btn-primary' : 'btn-secondary'"
        :disabled="!match.is_simulatable"
        @click="$emit('simulate', match)"
        :title="match.is_simulatable ? 'Run AI swarm simulation' : 'Match already completed'"
      >
        <span v-if="match.is_simulatable">Run Simulation</span>
        <span v-else>Completed</span>
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  match: {
    type: Object,
    required: true,
  },
  compact: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['simulate'])
</script>

<style scoped>
.match-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  transition: var(--transition);
  cursor: default;
}

.match-card:hover {
  border-color: var(--color-primary);
}

.match-card-compact {
  padding: 1rem;
}

.match-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
}

.match-teams-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.mc-team1 {
  font-weight: 700;
  font-size: 1.1rem;
  color: #6c63ff;
}

.mc-team2 {
  font-weight: 700;
  font-size: 1.1rem;
  color: #ff6584;
}

.mc-vs {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}

.match-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}

.mc-venue,
.mc-time,
.mc-city {
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

.mc-caveat {
  font-size: 0.75rem;
  color: var(--color-warning);
  margin-top: 0.25rem;
}

.match-card-footer {
  margin-top: auto;
}

.match-card-footer .btn {
  width: 100%;
}
</style>
