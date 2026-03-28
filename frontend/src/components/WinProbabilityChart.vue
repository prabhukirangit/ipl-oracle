<template>
  <div class="wpc-wrapper">
    <div class="chart-title">{{ title }}</div>
    <svg ref="svgEl" class="wpc-svg"></svg>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  title: { type: String, default: 'Win Probability' },
  // { TeamName: { win_pct, confidence_interval_95: { lower, upper } }, ... }
  winProbability: { type: Object, default: () => ({}) },
  predictedWinner: { type: String, default: '' },
})

const svgEl = ref(null)

const COLORS = {
  winner: '#4caf50',
  other: '#6c63ff',
  ci: 'rgba(255,255,255,0.15)',
}

function draw() {
  const el = svgEl.value
  if (!el) return

  const teams = Object.entries(props.winProbability)
    .filter(([k, v]) => k !== 'no_result' && typeof v === 'object')
    .map(([team, data]) => ({ team, ...data }))

  if (!teams.length) return

  const margin = { top: 8, right: 60, bottom: 8, left: 140 }
  const rowH = 44
  const totalH = teams.length * rowH + margin.top + margin.bottom
  const totalW = Math.max(280, el.parentElement?.clientWidth || 360)
  const width = totalW - margin.left - margin.right

  d3.select(el).selectAll('*').remove()

  const svg = d3.select(el)
    .attr('width', totalW)
    .attr('height', totalH)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`)

  const x = d3.scaleLinear().domain([0, 100]).range([0, width])

  teams.forEach((d, i) => {
    const y = i * rowH + rowH / 2
    const isWinner = d.team === props.predictedWinner
    const barColor = isWinner ? COLORS.winner : COLORS.other
    const ci = d.confidence_interval_95 || {}

    // Team name
    svg.append('text')
      .attr('x', -8)
      .attr('y', y + 4)
      .attr('text-anchor', 'end')
      .attr('fill', isWinner ? '#fff' : '#bbb')
      .attr('font-size', '12px')
      .attr('font-weight', isWinner ? '700' : '400')
      .text(d.team)

    // Background track
    svg.append('rect')
      .attr('x', 0)
      .attr('y', y - 10)
      .attr('width', width)
      .attr('height', 20)
      .attr('fill', 'rgba(255,255,255,0.04)')
      .attr('rx', 4)

    // CI range band
    if (ci.lower != null && ci.upper != null) {
      svg.append('rect')
        .attr('x', x(ci.lower))
        .attr('y', y - 10)
        .attr('width', x(ci.upper) - x(ci.lower))
        .attr('height', 20)
        .attr('fill', COLORS.ci)
        .attr('rx', 4)
    }

    // Win % bar
    svg.append('rect')
      .attr('x', 0)
      .attr('y', y - 7)
      .attr('width', 0)
      .attr('height', 14)
      .attr('fill', barColor)
      .attr('rx', 3)
      .transition()
      .duration(800)
      .ease(d3.easeCubicOut)
      .attr('width', x(d.win_pct))

    // % label
    svg.append('text')
      .attr('x', width + 6)
      .attr('y', y + 4)
      .attr('fill', barColor)
      .attr('font-size', '13px')
      .attr('font-weight', '700')
      .text(`${d.win_pct}%`)

    // CI label
    if (ci.lower != null) {
      svg.append('text')
        .attr('x', x(d.win_pct) + 4)
        .attr('y', y - 12)
        .attr('fill', '#666')
        .attr('font-size', '9px')
        .text(`CI ${ci.lower}–${ci.upper}%`)
    }
  })
}

onMounted(() => nextTick(draw))
watch(() => props.winProbability, draw, { deep: true })
</script>

<style scoped>
.wpc-wrapper {
  width: 100%;
}

.chart-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted, #999);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.wpc-svg {
  width: 100%;
  display: block;
  overflow: visible;
}
</style>
