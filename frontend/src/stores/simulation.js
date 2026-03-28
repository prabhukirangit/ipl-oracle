import { defineStore } from 'pinia'

export const useSimulationStore = defineStore('simulation', {
  state: () => ({
    activeSimId: null,
    activeTeams: null,
  }),
  getters: {
    isRunning: (state) => state.activeSimId !== null,
  },
  actions: {
    start(simId, team1, team2) {
      this.activeSimId = simId
      this.activeTeams = { team1, team2 }
    },
    finish() {
      this.activeSimId = null
      this.activeTeams = null
    },
  },
})
