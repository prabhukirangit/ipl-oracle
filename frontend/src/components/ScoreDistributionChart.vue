<template>
  <div class="chart-wrapper">
    <div class="chart-title">{{ title }}</div>
    <svg ref="svgEl" class="chart-svg"></svg>
    <div class="chart-legend">
      <span v-for="item in legendItems" :key="item.team" class="legend-item">
        <span class="legend-dot" :style="{ background: item.color }"></span>
        {{ item.team }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  title: { type: String, default: 'Score Distribution' },
  // { TeamName: [{ bin_start, bin_end, count }, ...], ... }
  histogramData: { type: Object, default: () => ({}) },
  scoreStats: { type: Object, default: () => ({}) },
})

const svgEl = ref(null)

const COLORS = ['#6c63ff', '#ff6584']
const legendItems = computed(() =>
  Object.keys(props.histogramData).map((team, i) => ({
    team,
    color: COLORS[i % COLORS.length],
  }))
)

function draw() {
  const el = svgEl.value
  if (!el) return

  const teams = Object.keys(props.histogramData)
  if (!teams.length) return

  // Flatten all bins to get overall x domain
  const allBins = teams.flatMap(t => props.histogramData[t] || [])
  if (!allBins.length) return

  const margin = { top: 12, right: 16, bottom: 36, left: 36 }
  const totalW = Math.max(300, el.parentElement?.clientWidth || 400)
  const width = totalW - margin.left - margin.right
  const height = 160 - margin.top - margin.bottom

  d3.select(el).selectAll('*').remove()

  const svg = d3.select(el)
    .attr('width', totalW)
    .attr('height', 160)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`)

  const xMin = d3.min(allBins, d => d.bin_start)
  const xMax = d3.max(allBins, d => d.bin_end)
  const yMax = d3.max(allBins, d => d.count)

  const x = d3.scaleLinear().domain([xMin, xMax]).range([0, width])
  const y = d3.scaleLinear().domain([0, yMax]).nice().range([height, 0])

  // Grid lines
  svg.append('g')
    .attr('class', 'grid')
    .call(d3.axisLeft(y).ticks(4).tickSize(-width).tickFormat(''))
    .select('.domain').remove()

  svg.selectAll('.grid line')
    .style('stroke', 'rgba(255,255,255,0.06)')
    .style('stroke-dasharray', '3,3')

  // Bars per team (side by side)
  const groupW = (x(xMax) - x(xMin)) / (allBins.length / teams.length)
  const barW = Math.max(2, (groupW / teams.length) - 2)

  teams.forEach((team, ti) => {
    const bins = props.histogramData[team] || []
    const color = COLORS[ti % COLORS.length]

    svg.selectAll(`.bar-${ti}`)
      .data(bins)
      .enter().append('rect')
      .attr('class', `bar-${ti}`)
      .attr('x', d => x(d.bin_start) + ti * (barW + 1))
      .attr('y', d => y(d.count))
      .attr('width', barW)
      .attr('height', d => height - y(d.count))
      .attr('fill', color)
      .attr('opacity', 0.75)
      .attr('rx', 2)

    // Median line
    const stats = props.scoreStats[team]
    if (stats?.median) {
      svg.append('line')
        .attr('x1', x(stats.median))
        .attr('x2', x(stats.median))
        .attr('y1', 0)
        .attr('y2', height)
        .attr('stroke', color)
        .attr('stroke-width', 1.5)
        .attr('stroke-dasharray', '4,3')
        .attr('opacity', 0.9)

      svg.append('text')
        .attr('x', x(stats.median) + 4)
        .attr('y', 10 + ti * 14)
        .attr('fill', color)
        .attr('font-size', '9px')
        .text(`med ${stats.median}`)
    }
  })

  // X axis
  svg.append('g')
    .attr('transform', `translate(0,${height})`)
    .call(d3.axisBottom(x).ticks(6).tickFormat(d => d))
    .select('.domain').style('stroke', 'rgba(255,255,255,0.2)')

  svg.selectAll('.tick line').style('stroke', 'rgba(255,255,255,0.2)')
  svg.selectAll('.tick text').style('fill', '#999').style('font-size', '10px')

  // X label
  svg.append('text')
    .attr('x', width / 2)
    .attr('y', height + 30)
    .attr('text-anchor', 'middle')
    .attr('fill', '#666')
    .attr('font-size', '10px')
    .text('Total score')
}

onMounted(() => nextTick(draw))
watch(() => props.histogramData, draw, { deep: true })
</script>

<style scoped>
.chart-wrapper {
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

.chart-svg {
  width: 100%;
  display: block;
  overflow: visible;
}

.chart-legend {
  display: flex;
  gap: 1rem;
  margin-top: 0.5rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.75rem;
  color: var(--color-text-muted, #999);
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
