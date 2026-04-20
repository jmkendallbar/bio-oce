// SYLLABUS_START
const weeks = [
  {w:1,title:"Discovering the oceans: history and overview of biological oceanography",ch:"Part 1",topics:["History of oceanographic exploration","From ancient mariners to satellite altimetry","Why study the ocean? Scale, heat capacity, and life support"]},
  {w:2,title:"Ocean basins: plate tectonics & bathymetry",ch:"Part 1",topics:["Seafloor spreading and mid-ocean ridges","Bathymetric provinces: shelf, slope, abyssal plain","Tools: multibeam sonar, seismic profiling"]},
  {w:3,title:"Seawater: Temperature, salinity, and density",ch:"Part 1",topics:["Conservative and non-conservative properties","Equation of state; density stratification","Dissolved gases; oxygen minimum zones"]},
  {w:4,title:"A spinning earth: coriolis effect, tides, gyres, currents, and eddies",ch:"Part 1",topics:["Earth's rotation, Ekman transport, and Ekman spirals","Geostrophic balance: tides and gyres","Western boundary current intensification"]},
  {w:5,title:"Ocean circulation: wind and density as drivers for ocean circulation",ch:"Part 1",topics:["Density gradients: permanent vs. seasonal pycnoclines","Wind, surface currents, upwelling, and downwelling","Consequences for global productivity"]},
  {w:6,title:"Nutrient circulation: movement and distribution of key nutrients",ch:"Part 2",topics:["Why the surface is light-rich but nutrient-poor","Subtropical gyres; ITCZ and trade winds","Thermohaline circulation and global heat transport"]},
  {w:7,title:"Life in the Ocean: life's origins, photosynthesis & primary productivity",ch:"Part 2",topics:["Light in the ocean: Beer–Lambert, euphotic depth","Phytoplankton physiology and growth kinetics","Monitoring NPP: Satellites and in-situ ROVs, CTDs, animal-borne sensors"]},
  {w:8,title:"Trophic flows in the ocean: energy, carbon & nutrients through the food web",ch:"Part 2",topics:["Food web topology; trophic efficiency (~10%)","Microbial loop and dissolved organic carbon","Redfield ratio and its significance"]},
  {w:9,title:"Midterm & Oscillations in physical processes: ENSO, PDO & variability",ch:"Part 2",topics:["ENSO mechanics: Walker circulation, thermocline tilt","PDO and its modulation of ENSO signal","Biological response in the California Current"]},
  {w:10,title:"Humans and the ocean: carbon cycle & the ocean's biological carbon pump",ch:"Part 3",topics:["From Mauna Loa to Station PAPA: Carbon dioxide over time","The ocean's biological carbon pump","Marine Carbon Dioxide Removal and Climate Mitigation"]},
  {w:11,title:"Ocean carbon chemistry & ocean acidification",ch:"Part 3",topics:["Carbonate system: CO₂, H₂CO₃, HCO₃⁻, CO₃²⁻","Revelle factor and buffering capacity","Ocean acidification: impacts on calcifiers"]},
  {w:12,title:"Fisheries science: population dynamics & management",ch:"Part 3",topics:["Surplus production models; MSY concept","Age-structured models; stock-recruitment","California Current fisheries and climate variability"]},
  {w:13,title:"Science to impact: data visualization to drive climate adaptation and mitigation",ch:"Part 3",topics:["Biodiversity monitoring: CalCOFI, IFCB, long-term time series","Carbon sequestration: biological pump and marine CDR","Nature-based solutions: NBS-Adapts, ShoreCast, coastal resilience"],current:true,hasLecture:true},
  {w:14,title:"Ocean ecosystems: holistic, dynamic management for ecosystems",ch:"Part 3",topics:["Environmental justice and traditional knowledge","Policy and management: challenges and opportunities","Guest lecture: Science to policy"]},
  {w:15,title:"Synthesis: The ocean in the Anthropocene",ch:"Part 3",topics:["AI for Ocean Sciences: challenges and opportunities","Final exam and student research presentation office hours","Student research presentations"]}
];
// SYLLABUS_END

const ensoData = {
  la:{label:'La Niña / Neutral',sst:[14.2,13.8,13.5,13.1,13.4,13.7,14.0,14.5,15.2,15.8,15.1,14.6],chl:[4.2,5.8,7.1,8.4,7.9,6.3,5.1,4.4,3.8,3.2,3.6,4.0],color:'#185FA5',desc:`<strong>La Niña / neutral:</strong> Strong trade winds push warm water west. Thermocline shoals off California — cold, nutrient-rich water upwells easily. Phytoplankton biomass elevated; diatoms dominate (<em>Pseudo-nitzschia</em>, <em>Chaetoceros</em>). High cell counts on IFCB. Fuels anchovy, sardine, krill, seabirds.`},
  el:{label:'El Niño 2015–16',sst:[16.8,17.2,17.5,17.9,18.3,18.1,17.6,17.2,16.9,16.4,16.1,16.5],chl:[1.4,1.8,2.0,1.6,1.5,1.7,1.9,1.8,1.6,1.5,1.6,1.5],color:'#E24B4A',desc:`<strong>El Niño 2015–16 (record strength):</strong> SSTs off California +2–3°C above average. Thermocline deepened to ~80–100 m. Upwelling drew from warm, nutrient-depleted layer. Diatom abundance collapsed; community shifted to small dinoflagellates. Sea lion strandings spiked; seabird breeding failures widespread.`},
  now:{label:'Spring 2026',sst:[14.8,14.3,13.9,13.6,13.9,14.2,14.6,15.1,15.7,16.2,15.5,15.0],chl:[3.6,5.0,6.4,7.8,7.2,5.8,4.7,4.0,3.5,3.0,3.3,3.7],color:'#1D9E75',desc:`<strong>Spring 2026 — near-neutral / weak La Niña:</strong> SSTs within normal range. Upwelling season underway — the IFCB at Scripps Pier is capturing the early spring diatom bloom. Compare today's community to what you'd expect during an El Niño year using the live dashboard.`}
};

let currentENSO = 'la';
let ensoChart = null;
let ifcbChart = null;

window.addEventListener('DOMContentLoaded', () => {
  buildSyllabus();
  buildWeek13Sidebar();
  initWeek13Sidebar();
  if (document.getElementById('ensoChart') && document.getElementById('ensoDesc')) {
    setENSO('la');
  }
  const loadBtn = document.getElementById('loadIfcbSample');
  if (loadBtn) {
    loadBtn.addEventListener('click', loadCalcofiIfcbSample);
    loadCalcofiIfcbSample();
  }
});

function buildWeek13Sidebar() {
  const list = document.getElementById('week13LectureList');
  if (!list) return;
  list.innerHTML = '';
  weeks.forEach(w => {
    const item = document.createElement('li');
    item.className = 'week13-lecture-item' + (w.w === 13 ? ' current' : '');
    item.textContent = `Week ${w.w} — ${w.title}`;
    if (w.w === 13) {
      const sub = document.createElement('ul');
      sub.className = 'week13-subnav';
      sub.innerHTML = `
        <li><a href="#week13-plankton-activity">Plankton ID Activity</a></li>
        <li><a href="#week13-timeseries">Santa Cruz Wharf Timeseries</a></li>
        <li><a href="#week13-video-gallery">Video Gallery</a></li>
      `;
      item.appendChild(sub);
    }
    list.appendChild(item);
  });
}

function initWeek13Sidebar() {
  const lecturePage = document.getElementById('page-lecture');
  if (lecturePage) {
    lecturePage.querySelectorAll('.week13-subnav a').forEach(link => {
      link.addEventListener('click', () => {
        closeWeek13Sidebar();
      });
    });
  }
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeWeek13Sidebar();
    }
  });
  updateWeek13MenuVisibility('syllabus');
}

function getWeek13Shell() {
  return document.querySelector('#page-lecture .week13-shell');
}

function openWeek13Sidebar() {
  const shell = getWeek13Shell();
  if (!shell) return;
  shell.classList.add('sidebar-open');
  document.body.classList.add('week13-sidebar-open');
}

function closeWeek13Sidebar() {
  const shell = getWeek13Shell();
  if (!shell) return;
  shell.classList.remove('sidebar-open');
  document.body.classList.remove('week13-sidebar-open');
}

function toggleWeek13Sidebar(event) {
  if (event) event.preventDefault();
  if (document.body.classList.contains('week13-sidebar-open')) {
    closeWeek13Sidebar();
  } else {
    openWeek13Sidebar();
  }
}

function updateWeek13MenuVisibility(activePageId) {
  const menuButton = document.getElementById('week13MenuBtn');
  if (!menuButton) return;
  const shouldShow = activePageId === 'lecture';
  document.body.classList.toggle('week13-view-active', shouldShow);
  menuButton.classList.toggle('visible', shouldShow);
  if (shouldShow) {
    openWeek13Sidebar();
  } else {
    closeWeek13Sidebar();
  }
}

function toggleLectureSections(event) {
  if (event) event.preventDefault();
  const navBlock = document.getElementById('week13NavBlock');
  const toggle = document.getElementById('week13LectureToggle');
  if (!navBlock || !toggle) return;
  const nowCollapsed = navBlock.classList.toggle('lecture-collapsed');
  toggle.setAttribute('aria-expanded', String(!nowCollapsed));
  toggle.textContent = nowCollapsed ? 'Show All' : 'Focus Week 13';
}

function buildSyllabus() {
  const list = document.getElementById('weekList');
  weeks.forEach(w => {
    const card = document.createElement('div');
    card.className = 'week-card' + (w.current ? ' highlight' : '');
    card.innerHTML = `
      <div class="week-header" onclick="toggleWeek(this)">
        <span class="week-badge${w.current ? ' current' : ''}">Wk ${w.w}</span>
        <span class="week-title">${w.title}</span>
        <span class="week-chapter">${w.ch}</span>
        <svg class="week-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="week-detail">
        <ul>${w.topics.map(t => `<li>${t}</li>`).join('')}</ul>
        ${w.hasLecture ? `<button class="lecture-link" onclick="showPage(event,'lecture')">→ Open Week 13 data lecture</button>` : ''}
      </div>`;
    list.appendChild(card);
  });
}

function toggleWeek(header) {
  header.parentElement.classList.toggle('open');
}

function showPage(event, id) {
  document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(button => button.classList.toggle('active', button.dataset.page === id));
  document.getElementById('page-' + id).classList.add('active');
  updateWeek13MenuVisibility(id);
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (id === 'lecture') {
    document.getElementById('nav-lecture').classList.add('active');
  }
}

function showSection(event, id) {
  document.querySelectorAll('.lecture-section').forEach(section => section.classList.remove('active'));
  document.querySelectorAll('.stab').forEach(tab => tab.classList.remove('active'));
  document.getElementById('sec-' + id).classList.add('active');
  event.currentTarget.classList.add('active');
}

function playYT(card, id) {
  card.classList.add('playing');
  const iframe = card.querySelector('iframe');
  iframe.src = `https://www.youtube.com/embed/${id}?autoplay=1`;
}

function setENSO(state) {
  currentENSO = state;
  document.querySelectorAll('.etbtn').forEach(button => {
    button.classList.remove('active-la', 'active-el', 'active-now');
  });
  const activeButton = document.getElementById('btn-' + state);
  if (activeButton) activeButton.classList.add('active-' + state);
  renderENSO();
}

function renderENSO() {
  const d = ensoData[currentENSO];
  const ensoCanvas = document.getElementById('ensoChart');
  const ensoDesc = document.getElementById('ensoDesc');
  if (!ensoCanvas || !ensoDesc || typeof Chart === 'undefined') return;
  const ctx = ensoCanvas.getContext('2d');
  const months = ['J','F','M','A','M','J','J','A','S','O','N','D'];
  if (ensoChart) {
    ensoChart.destroy();
  }
  ensoChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: months,
      datasets: [
        {
          type: 'line',
          label: 'SST (°C)',
          data: d.sst,
          borderColor: d.color,
          backgroundColor: d.color + '33',
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 4,
          yAxisID: 'y1'
        },
        {
          label: 'Chlorophyll (relative)',
          data: d.chl,
          backgroundColor: '#1D9E7555',
          borderColor: '#1D9E75',
          borderWidth: 1,
          yAxisID: 'y2'
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { font: { size: 11 }, boxWidth: 12 } } },
      scales: {
        y1: { type: 'linear', position: 'left', title: { display: true, text: 'SST (°C)', font: { size: 11 } }, min: 12, max: 20 },
        y2: { type: 'linear', position: 'right', title: { display: true, text: 'Chlorophyll (relative)', font: { size: 11 } }, grid: { drawOnChartArea: false }, min: 0, max: 10 }
      }
    }
  });
  ensoDesc.innerHTML = d.desc;
}

function checkHypothesis() {
  const input = document.getElementById('hypoInput');
  const feedback = document.getElementById('hypoFeedback');
  if (!input || !feedback) return;
  if (!input.value.trim() || input.value.trim().length < 20) {
    feedback.innerHTML = 'Write a complete hypothesis first. Focus on mechanism: wind, stratification, nutrients, and community response.';
    feedback.style.display = 'block';
    return;
  }
  feedback.style.display = 'block';
  feedback.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function loadCalcofiIfcbSample() {
  const status = document.getElementById('ifcbStatus');
  if (!status) return;
  status.textContent = 'Loading sample CalCOFI / IFCB dataset...';
  try {
    const response = await fetch('data/calcofi_ifcb_sample.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderCalcofiIfcbData(data);
    status.innerHTML = 'Sample dataset loaded. Replace <code>data/calcofi_ifcb_sample.json</code> with real CalCOFI / IFCB JSON to power the dashboard.';
  } catch (error) {
    status.innerHTML = 'Unable to load sample dataset. Check browser console for errors.';
    console.error('CalCOFI/IFCB sample load failed:', error);
  }
}

function renderCalcofiIfcbData(data) {
  const years = data.calcofi?.years || [];
  const chlorophyll = data.calcofi?.sbl_chlorophyll || [];
  const nitrate = data.calcofi?.nitrate || [];
  const totalCells = data.ifcb?.total_cells || [];
  const dates = data.ifcb?.dates || [];
  const diatoms = data.ifcb?.diatoms || [];
  const flagellates = data.ifcb?.flagellates || [];

  const metricChl = document.getElementById('ifcbMetricChl');
  const metricNitrate = document.getElementById('ifcbMetricNitrate');
  const metricTotal = document.getElementById('ifcbMetricTotal');
  const breakdown = document.getElementById('ifcbBreakdown');
  if (metricChl) metricChl.textContent = chlorophyll.length ? `${chlorophyll[chlorophyll.length - 1].toFixed(2)} µg/L` : 'No data';
  if (metricNitrate) metricNitrate.textContent = nitrate.length ? `${nitrate[nitrate.length - 1].toFixed(1)} µM` : 'No data';
  if (metricTotal) metricTotal.textContent = totalCells.length ? `${totalCells[totalCells.length - 1].toLocaleString()} cells/mL` : 'No data';
  if (breakdown) {
    breakdown.innerHTML = `IFCB sample dates: ${dates.length ? dates.join(', ') : 'no values'}<br><strong>Diatoms:</strong> ${diatoms.length ? diatoms.join(', ') : '–'}<br><strong>Flagellates:</strong> ${flagellates.length ? flagellates.join(', ') : '–'}`;
  }

  const ifcbCanvas = document.getElementById('ifcbChart');
  if (!ifcbCanvas || typeof Chart === 'undefined') return;
  const ctx = ifcbCanvas.getContext('2d');
  if (ifcbChart) ifcbChart.destroy();
  ifcbChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: years.map(String),
      datasets: [
        {
          label: 'CalCOFI chlorophyll (µg/L)',
          data: chlorophyll,
          borderColor: '#185FA5',
          backgroundColor: '#185FA533',
          tension: 0.35,
          fill: true,
          yAxisID: 'y1'
        },
        {
          label: 'CalCOFI nitrate (µM)',
          data: nitrate,
          borderColor: '#1D9E75',
          backgroundColor: '#1D9E755',
          tension: 0.35,
          fill: false,
          yAxisID: 'y2'
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top' } },
      scales: {
        y1: { type: 'linear', position: 'left', title: { display: true, text: 'Chlorophyll (µg/L)' } },
        y2: { type: 'linear', position: 'right', title: { display: true, text: 'Nitrate (µM)' }, grid: { drawOnChartArea: false } }
      }
    }
  });
}
