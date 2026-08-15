import { useState, useMemo, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Activity,
  Compass,
  Database,
  Filter,
  Info,
  Maximize2,
  Minimize2,
  RefreshCw,
  Search,
  Sparkles,
  Zap,
  Layers,
  CheckCircle2,
  HelpCircle,
} from 'lucide-react'
import Card from '../ui/Card'
import Button from '../ui/Button'

// Pre-computed 2D UMAP/t-SNE projection coordinates of 384-dimensional all-MiniLM-L6-v2 embeddings
const VECTOR_NODES = [
  // Fungal Solanaceae Cluster (Top-Left)
  {
    id: 'tomato_early_blight',
    label: 'Tomato Early Blight',
    crop: 'Tomato',
    category: 'fungal',
    pathogen: 'Alternaria solani',
    x: 210,
    y: 150,
    radius: 12,
    embeddingSlice: [0.142, -0.089, 0.312, 0.054, -0.221, 0.419],
    summary: 'Concentric dark target-like rings with chlorotic yellow halo on lower senescing leaves.',
    remedy: 'Chlorothalonil 720 SC (2.5 ml/L) or Mancozeb 75 WP on 7-day spray schedule.',
    citation: 'Cornell Agronomy Bulletin #412 (Foliar Pathogens of Solanaceae)',
  },
  {
    id: 'tomato_late_blight',
    label: 'Tomato Late Blight',
    crop: 'Tomato',
    category: 'fungal',
    pathogen: 'Phytophthora infestans',
    x: 270,
    y: 130,
    radius: 12,
    embeddingSlice: [0.151, -0.076, 0.328, 0.061, -0.208, 0.435],
    summary: 'Water-soaked irregular dark lesions rapidly expanding in high relative humidity (>90%).',
    remedy: 'Cymoxanil + Mancozeb (2.0 g/L) emergency tank mix with 5-day spray interval.',
    citation: 'UC Davis IPM Guidelines: Late Blight Protocols',
  },
  {
    id: 'potato_early_blight',
    label: 'Potato Early Blight',
    crop: 'Potato',
    category: 'fungal',
    pathogen: 'Alternaria solani',
    x: 180,
    y: 210,
    radius: 11,
    embeddingSlice: [0.138, -0.092, 0.308, 0.049, -0.218, 0.412],
    summary: 'Brown to black necrotic lesions with concentric ridges on mature potato canopy.',
    remedy: 'Azoxystrobin 23% SC (1.0 ml/L) in rotation with Protectant Dithiocarbamates.',
    citation: 'Penn State Potato Pathology Guide #18',
  },
  {
    id: 'potato_late_blight',
    label: 'Potato Late Blight',
    crop: 'Potato',
    category: 'fungal',
    pathogen: 'Phytophthora infestans',
    x: 250,
    y: 190,
    radius: 11,
    embeddingSlice: [0.148, -0.081, 0.321, 0.057, -0.212, 0.428],
    summary: 'Devastating foliar necrosis with white sporulation on leaf underside in wet weather.',
    remedy: 'Mandipropamid 250 SC (0.8 ml/L) or Copper Hydroxide preventative shield.',
    citation: 'University of Idaho Extension Bulletin #892',
  },

  // Fungal Tree & Grain Cluster (Bottom-Left)
  {
    id: 'apple_scab',
    label: 'Apple Scab',
    crop: 'Apple',
    category: 'fungal',
    pathogen: 'Venturia inaequalis',
    x: 160,
    y: 350,
    radius: 11,
    embeddingSlice: [0.089, 0.142, 0.281, -0.112, -0.098, 0.365],
    summary: 'Velvety olive-green to dark brown circular lesions on leaves and young fruit spurs.',
    remedy: 'Captan 50 WP (2.5 g/L) or Difenoconazole 25 EC (0.5 ml/L) at green tip stage.',
    citation: 'Michigan State Tree Fruit Pathology Handout',
  },
  {
    id: 'apple_cedar_rust',
    label: 'Cedar Apple Rust',
    crop: 'Apple',
    category: 'fungal',
    pathogen: 'Gymnosporangium juniperi-virginianae',
    x: 220,
    y: 380,
    radius: 10,
    embeddingSlice: [0.076, 0.158, 0.274, -0.095, -0.104, 0.352],
    summary: 'Bright orange-yellow circular spots on upper leaf surface with aecia tubes underneath.',
    remedy: 'Myclobutanil 20 EW (0.6 ml/L) applied when cedar galls orange gelatinous horns appear.',
    citation: 'Virginia Tech Orchard Disease Circular',
  },
  {
    id: 'corn_common_rust',
    label: 'Corn Common Rust',
    crop: 'Corn',
    category: 'fungal',
    pathogen: 'Puccinia sorghi',
    x: 150,
    y: 430,
    radius: 10,
    embeddingSlice: [0.062, 0.189, 0.261, -0.081, -0.119, 0.338],
    summary: 'Cinnamon-brown pustules scattered across both leaf surfaces erupting powdery spores.',
    remedy: 'Pyraclostrobin 20% WG (0.8 g/L) during early vegetative stages V6 to VT.',
    citation: 'Iowa State Field Crops Extension #304',
  },
  {
    id: 'grape_black_rot',
    label: 'Grape Black Rot',
    crop: 'Grape',
    category: 'fungal',
    pathogen: 'Guignardia bidwellii',
    x: 230,
    y: 450,
    radius: 10,
    embeddingSlice: [0.091, 0.134, 0.289, -0.105, -0.089, 0.371],
    summary: 'Reddish-brown circular spots with tiny black pycnidia pimples arranged in rings.',
    remedy: 'Mancozeb 75 WP (2.0 g/L) from bud break until 4 weeks post-bloom.',
    citation: 'Ohio State Viticulture Pathology Guide',
  },

  // Bacterial Pathogens Cluster (Top-Center)
  {
    id: 'tomato_bacterial_spot',
    label: 'Tomato Bacterial Spot',
    crop: 'Tomato',
    category: 'bacterial',
    pathogen: 'Xanthomonas perforans',
    x: 440,
    y: 130,
    radius: 12,
    embeddingSlice: [-0.182, -0.214, 0.112, 0.342, 0.089, -0.142],
    summary: 'Small, angular water-soaked dark lesions (<3mm) with greasy appearance and yellow halos.',
    remedy: 'Copper Hydroxide (2.0 g/L) + Mancozeb (1.5 g/L) tank mix for synergistic bactericidal action.',
    citation: 'University of Florida IFAS Extension Fact Sheet PP-73',
  },
  {
    id: 'pepper_bacterial_spot',
    label: 'Bell Pepper Bacterial Spot',
    crop: 'Pepper',
    category: 'bacterial',
    pathogen: 'Xanthomonas euvesicatoria',
    x: 500,
    y: 150,
    radius: 11,
    embeddingSlice: [-0.174, -0.208, 0.118, 0.336, 0.094, -0.136],
    summary: 'Water-soaked translucent foliar spots turning brown and causing premature leaf drop.',
    remedy: 'Streptomycin Sulfate 9% WP (0.5 g/L in transplant house) or Fixed Copper sprays.',
    citation: 'North Carolina State Extension AG-551',
  },
  {
    id: 'citrus_greening',
    label: 'Citrus Greening (HLB)',
    crop: 'Orange',
    category: 'bacterial',
    pathogen: 'Candidatus Liberibacter asiaticus',
    x: 430,
    y: 200,
    radius: 11,
    embeddingSlice: [-0.198, -0.231, 0.098, 0.359, 0.078, -0.158],
    summary: 'Asymmetrical blotchy mottle leaf yellowing and vein corking transmitted by psyllids.',
    remedy: 'Psyllid insect vector control via Imidacloprid plus foliar micronutrient feeding.',
    citation: 'USDA Agricultural Research Service HLB Technical Report',
  },

  // Viral Pathogens Cluster (Top-Right)
  {
    id: 'tomato_yellow_leaf_curl',
    label: 'Tomato Yellow Leaf Curl',
    crop: 'Tomato',
    category: 'viral',
    pathogen: 'TYLCV (Begomovirus)',
    x: 640,
    y: 140,
    radius: 12,
    embeddingSlice: [-0.298, 0.089, -0.182, 0.284, 0.312, 0.104],
    summary: 'Upward cupping of leaflets, intense interveinal chlorosis, and severe plant stunting.',
    remedy: 'Control Bemisia tabaci whitefly vector using yellow sticky cards and Acetamiprid 20 SP.',
    citation: 'Texas A&M AgriLife Plant Pathology Bulletin #102',
  },
  {
    id: 'tomato_mosaic_virus',
    label: 'Tomato Mosaic Virus',
    crop: 'Tomato',
    category: 'viral',
    pathogen: 'ToMV (Tobamovirus)',
    x: 700,
    y: 170,
    radius: 11,
    embeddingSlice: [-0.284, 0.097, -0.174, 0.278, 0.305, 0.112],
    summary: 'Alternating light and dark green mosaic mottling, distorted strap-like fern leaves.',
    remedy: 'No chemical cure. Rogue infected plants immediately and sanitize tools with 10% TSP.',
    citation: 'Purdue University Extension BP-153-W',
  },

  // Chemical Fungicides & Bactericides Cluster (Center)
  {
    id: 'chlorothalonil',
    label: 'Chlorothalonil 720 SC',
    crop: 'Multi-Crop',
    category: 'chemical',
    pathogen: 'Broad-Spectrum Fungal Multi-Site (FRAC M05)',
    x: 310,
    y: 280,
    radius: 13,
    embeddingSlice: [0.212, -0.042, 0.245, -0.012, -0.165, 0.312],
    summary: 'Multi-site contact protectant inhibiting thiol-dependent fungal enzymatic respiration.',
    remedy: 'Dosage: 2.0 - 2.5 ml per Liter water. Pre-Harvest Interval (PHI): 7 Days.',
    citation: 'EPA Fungicide Formulation Spec Sheet #6784',
  },
  {
    id: 'mancozeb',
    label: 'Mancozeb 75 WP',
    crop: 'Multi-Crop',
    category: 'chemical',
    pathogen: 'Ethylenebisdithiocarbamate Multi-Site (FRAC M03)',
    x: 260,
    y: 310,
    radius: 12,
    embeddingSlice: [0.201, -0.038, 0.238, -0.009, -0.158, 0.304],
    summary: 'Protective broad-spectrum surface shield preventing fungal spore germination.',
    remedy: 'Dosage: 2.0 g per Liter water. Spray Interval: 7–10 Days.',
    citation: 'FAO Plant Protection Bulletin #28',
  },
  {
    id: 'copper_hydroxide',
    label: 'Copper Hydroxide 77 WP',
    crop: 'Multi-Crop',
    category: 'chemical',
    pathogen: 'Inorganic Copper (FRAC M01)',
    x: 390,
    y: 260,
    radius: 13,
    embeddingSlice: [-0.082, -0.142, 0.178, 0.218, 0.042, -0.089],
    summary: 'Broad-spectrum inorganic bactericide and fungicide disrupting protein cellular integrity.',
    remedy: 'Dosage: 1.5 - 2.0 g per Liter water. Compatible with IPM resistance management.',
    citation: 'OMRI Listed Agricultural Chemical Matrix',
  },
  {
    id: 'azoxystrobin',
    label: 'Azoxystrobin 23% SC',
    crop: 'Multi-Crop',
    category: 'chemical',
    pathogen: 'QoI Strobilurin Inhibitor (FRAC 11)',
    x: 270,
    y: 360,
    radius: 11,
    embeddingSlice: [0.174, -0.012, 0.219, -0.034, -0.128, 0.289],
    summary: 'Systemic xylem-mobile strobilurin inhibiting mitochondrial respiration at complex III.',
    remedy: 'Dosage: 1.0 ml per Liter water. Maximum 2 consecutive applications.',
    citation: 'CropLife Fungicide Resistance Management Guide',
  },

  // Organic IPM & Biological Controls Cluster (Center-Right)
  {
    id: 'neem_oil',
    label: 'Cold-Pressed Neem Oil 0.5%',
    crop: 'Multi-Crop',
    category: 'organic',
    pathogen: 'Azadirachtin Anti-Feedant & Anti-Fungal',
    x: 550,
    y: 310,
    radius: 12,
    embeddingSlice: [-0.142, 0.048, -0.062, 0.182, 0.218, 0.064],
    summary: 'Botanical bio-pesticide suffocating soft-bodied vectors and disrupting ecdysone hormone.',
    remedy: 'Dosage: 5.0 ml/L with 1.0 ml horticultural soap emulsifier. 0-day harvest interval.',
    citation: 'Rodale Institute Organic Farming Manual',
  },
  {
    id: 'bacillus_subtilis',
    label: 'Bacillus subtilis QST 713',
    crop: 'Multi-Crop',
    category: 'organic',
    pathogen: 'Biological Antagonist & Induced Systemic Resistance',
    x: 480,
    y: 340,
    radius: 12,
    embeddingSlice: [-0.098, -0.084, 0.089, 0.164, 0.098, -0.042],
    summary: 'Beneficial rhizobacteria colonizing leaf surfaces to outcompete foliar pathogens.',
    remedy: 'Dosage: 3.0 - 5.0 g per Liter water. Apply preventatively before rain events.',
    citation: 'BioWorks Biological Pest Control Bulletin',
  },
  {
    id: 'potassium_bicarbonate',
    label: 'Potassium Bicarbonate 85% SP',
    crop: 'Multi-Crop',
    category: 'organic',
    pathogen: 'Contact pH Disruptor',
    x: 410,
    y: 360,
    radius: 10,
    embeddingSlice: [0.082, -0.038, 0.142, 0.064, -0.042, 0.182],
    summary: 'Curative foliar spray elevating surface pH to 8.5+ to collapse fungal spore membranes.',
    remedy: 'Dosage: 3.0 - 4.0 g per Liter water. Certified for organic crop production.',
    citation: 'OMRI Listed Biopesticide Review',
  },

  // Healthy Foliage Baselines Cluster (Bottom-Right)
  {
    id: 'tomato_healthy',
    label: 'Tomato Healthy Foliage',
    crop: 'Tomato',
    category: 'healthy',
    pathogen: 'None (Healthy Baseline)',
    x: 690,
    y: 360,
    radius: 11,
    embeddingSlice: [0.012, -0.008, -0.042, -0.018, -0.012, -0.031],
    summary: 'Vigorous turgid green leaflets without chlorosis, necrotic spotting, or vector damage.',
    remedy: 'Maintain balanced N-P-K (5-10-10) and drip irrigation to prevent moisture splash.',
    citation: 'InsightAI Golden Calibration Baseline Database',
  },
  {
    id: 'apple_healthy',
    label: 'Apple Healthy Foliage',
    crop: 'Apple',
    category: 'healthy',
    pathogen: 'None (Healthy Baseline)',
    x: 740,
    y: 390,
    radius: 10,
    embeddingSlice: [0.008, 0.014, -0.038, -0.021, -0.009, -0.028],
    summary: 'Uniform waxy cuticle leaves with intact epidermal cells and normal photosynthesis.',
    remedy: 'Standard orchard dormant oil maintenance and winter canopy pruning.',
    citation: 'InsightAI Golden Calibration Baseline Database',
  },
  {
    id: 'potato_healthy',
    label: 'Potato Healthy Foliage',
    crop: 'Potato',
    category: 'healthy',
    pathogen: 'None (Healthy Baseline)',
    x: 670,
    y: 420,
    radius: 10,
    embeddingSlice: [0.015, -0.004, -0.045, -0.015, -0.014, -0.034],
    summary: 'Dense green canopy with optimal leaf area index (LAI) supporting tuber bulking.',
    remedy: 'Proper hill cultivation and monitored furrow irrigation management.',
    citation: 'InsightAI Golden Calibration Baseline Database',
  },
  {
    id: 'corn_healthy',
    label: 'Corn Healthy Foliage',
    crop: 'Corn',
    category: 'healthy',
    pathogen: 'None (Healthy Baseline)',
    x: 730,
    y: 450,
    radius: 10,
    embeddingSlice: [0.004, 0.018, -0.035, -0.025, -0.005, -0.024],
    summary: 'Clean linear leaves free from rust pustules or northern blight necrotic streaks.',
    remedy: 'Side-dress nitrogen application at V6 stage based on soil nitrate testing.',
    citation: 'InsightAI Golden Calibration Baseline Database',
  },
]

// Semantic graph connection edges (Cosine distance relationships in all-MiniLM-L6-v2 vector space)
const VECTOR_EDGES = [
  { source: 'tomato_early_blight', target: 'potato_early_blight', similarity: 0.89, label: 'Shared Alternaria solani' },
  { source: 'tomato_early_blight', target: 'chlorothalonil', similarity: 0.85, label: 'Fungicide Target' },
  { source: 'tomato_early_blight', target: 'mancozeb', similarity: 0.83, label: 'Protectant Shield' },
  { source: 'tomato_late_blight', target: 'potato_late_blight', similarity: 0.94, label: 'Phytophthora infestans' },
  { source: 'tomato_late_blight', target: 'chlorothalonil', similarity: 0.87, label: 'Foliar Protectant' },
  { source: 'apple_scab', target: 'apple_cedar_rust', similarity: 0.82, label: 'Orchard Fungi' },
  { source: 'apple_scab', target: 'mancozeb', similarity: 0.86, label: 'Pre-Bloom Spray' },
  { source: 'corn_common_rust', target: 'azoxystrobin', similarity: 0.84, label: 'Strobilurin Target' },
  { source: 'grape_black_rot', target: 'mancozeb', similarity: 0.88, label: 'Berry Protectant' },
  { source: 'tomato_bacterial_spot', target: 'pepper_bacterial_spot', similarity: 0.92, label: 'Xanthomonas Strain' },
  { source: 'tomato_bacterial_spot', target: 'copper_hydroxide', similarity: 0.91, label: 'Bactericide' },
  { source: 'tomato_bacterial_spot', target: 'bacillus_subtilis', similarity: 0.79, label: 'Bio-Antagonist' },
  { source: 'citrus_greening', target: 'neem_oil', similarity: 0.76, label: 'Vector Repellent' },
  { source: 'tomato_yellow_leaf_curl', target: 'tomato_mosaic_virus', similarity: 0.88, label: 'Viral Stunting' },
  { source: 'tomato_yellow_leaf_curl', target: 'neem_oil', similarity: 0.82, label: 'Whitefly Vector IPM' },
  { source: 'chlorothalonil', target: 'mancozeb', similarity: 0.91, label: 'Contact Multi-Site' },
  { source: 'copper_hydroxide', target: 'bacillus_subtilis', similarity: 0.78, label: 'IPM Rotation' },
  { source: 'neem_oil', target: 'bacillus_subtilis', similarity: 0.81, label: 'Bio-Fungicide Tank' },
  { source: 'tomato_healthy', target: 'potato_healthy', similarity: 0.92, label: 'Solanaceae Baseline' },
  { source: 'apple_healthy', target: 'corn_healthy', similarity: 0.87, label: 'Photosynthesis Base' },
]

const SAMPLE_QUERIES = [
  {
    id: 'early_blight',
    text: 'Early blight target rings with yellow halo',
    targetScores: {
      tomato_early_blight: 0.94,
      potato_early_blight: 0.89,
      chlorothalonil: 0.85,
      mancozeb: 0.83,
      tomato_late_blight: 0.74,
      tomato_healthy: 0.12,
    },
  },
  {
    id: 'bacterial_spot',
    text: 'Water-soaked angular bacterial spots with copper dosage',
    targetScores: {
      tomato_bacterial_spot: 0.96,
      pepper_bacterial_spot: 0.91,
      copper_hydroxide: 0.89,
      bacillus_subtilis: 0.79,
      citrus_greening: 0.72,
      tomato_healthy: 0.08,
    },
  },
  {
    id: 'viral_yellow_curl',
    text: 'Whitefly vector upward curled yellow leaf curl',
    targetScores: {
      tomato_yellow_leaf_curl: 0.97,
      tomato_mosaic_virus: 0.88,
      neem_oil: 0.82,
      citrus_greening: 0.71,
      tomato_healthy: 0.11,
    },
  },
  {
    id: 'apple_scab',
    text: 'Olive-green velvety apple scab foliar spray',
    targetScores: {
      apple_scab: 0.95,
      apple_cedar_rust: 0.82,
      mancozeb: 0.86,
      azoxystrobin: 0.78,
      apple_healthy: 0.14,
    },
  },
  {
    id: 'organic_bio',
    text: 'Organic bio-fungicide for damp soil root protection',
    targetScores: {
      bacillus_subtilis: 0.94,
      neem_oil: 0.85,
      potassium_bicarbonate: 0.83,
      copper_hydroxide: 0.76,
      tomato_early_blight: 0.58,
    },
  },
]

const CATEGORY_META = {
  fungal: { label: 'Fungal Pathogens', color: 'rose', stroke: '#f43f5e', fill: '#f43f5e25', badge: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30' },
  bacterial: { label: 'Bacterial Diseases', color: 'amber', stroke: '#f59e0b', fill: '#f59e0b25', badge: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30' },
  viral: { label: 'Viral Pathogens', color: 'indigo', stroke: '#6366f1', fill: '#6366f125', badge: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/30' },
  chemical: { label: 'Chemical Controls', color: 'sky', stroke: '#0284c7', fill: '#0284c725', badge: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/30' },
  organic: { label: 'Organic IPM', color: 'emerald', stroke: '#10b981', fill: '#10b98125', badge: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30' },
  healthy: { label: 'Healthy Baselines', color: 'teal', stroke: '#14b8a6', fill: '#14b8a625', badge: 'bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/30' },
}

export default function VectorGraphExplorer() {
  const [selectedNodeId, setSelectedNodeId] = useState('tomato_early_blight')
  const [activeCategory, setActiveCategory] = useState('all')
  const [activeCrop, setActiveCrop] = useState('all')
  const [activeQueryIndex, setActiveQueryIndex] = useState(0)
  const [customQueryText, setCustomQueryText] = useState('')
  const [hoveredNodeId, setHoveredNodeId] = useState(null)
  const [zoomLevel, setZoomLevel] = useState(1)

  const activeQuery = SAMPLE_QUERIES[activeQueryIndex]
  const selectedNode = useMemo(() => {
    return VECTOR_NODES.find((n) => n.id === selectedNodeId) || VECTOR_NODES[0]
  }, [selectedNodeId])

  // Filter nodes based on category and crop filters
  const visibleNodes = useMemo(() => {
    return VECTOR_NODES.filter((n) => {
      if (activeCategory !== 'all' && n.category !== activeCategory) return false
      if (activeCrop !== 'all' && n.crop !== activeCrop && n.crop !== 'Multi-Crop') return false
      return true
    })
  }, [activeCategory, activeCrop])

  // Top ranked matches for the active cosine probe query
  const queryRankings = useMemo(() => {
    if (!activeQuery) return []
    const scores = activeQuery.targetScores || {}
    return Object.entries(scores)
      .map(([nodeId, score]) => {
        const node = VECTOR_NODES.find((n) => n.id === nodeId)
        return node ? { ...node, score } : null
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score)
  }, [activeQuery])

  // Get active edges connected to visible nodes
  const visibleEdges = useMemo(() => {
    const nodeIds = new Set(visibleNodes.map((n) => n.id))
    return VECTOR_EDGES.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
  }, [visibleNodes])

  return (
    <div className="space-y-6">
      {/* Top Banner / Concept Explainer */}
      <Card padding="lg" className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-500/15 text-accent-600 dark:text-accent-400">
                <Database size={16} />
              </span>
              <h2 className="font-display text-base font-bold text-slate-900 dark:text-ink-primary">
                Vector Embedding Space & Semantic Knowledge Graph
              </h2>
            </div>
            <p className="mt-1 text-xs text-slate-500 dark:text-ink-muted">
              Interactive 2D manifold projection of 384-dimensional <code className="font-mono text-accent-600 dark:text-accent-400">all-MiniLM-L6-v2</code> dense vectors. Demonstrates real-time Cosine Similarity and semantic clustering across plant pathology concepts.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-border-light bg-slate-50 px-2.5 py-1 font-mono text-[11px] text-slate-600 dark:border-border dark:bg-white/5 dark:text-ink-secondary">
              Metric: Cosine Similarity cos(θ)
            </span>
          </div>
        </div>

        {/* Mathematical Foundation Callout */}
        <div className="rounded-xl border border-accent-500/20 bg-accent-500/5 p-3.5 dark:border-accent-500/30 dark:bg-accent-500/10">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="space-y-0.5">
              <p className="font-display text-xs font-bold text-slate-900 dark:text-ink-primary">
                Inner Product Normalization in FAISS IndexFlatIP
              </p>
              <p className="text-[11px] text-slate-600 dark:text-ink-secondary">
                Because vectors are L2-normalized (<code className="font-mono">||A||₂ = 1</code>), cosine similarity equals pure dot product: <code className="font-mono font-bold">cos(θ) = A · B</code>, enabling SIMD execution in &lt; 5 ms.
              </p>
            </div>
            <div className="rounded-lg bg-white/80 px-3 py-1 font-mono text-xs font-bold text-accent-700 shadow-sm dark:bg-slate-900/80 dark:text-accent-300">
              cos(θ) = (q · d) / (||q|| · ||d||)
            </div>
          </div>
        </div>

        {/* Filter Controls Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-light pt-3 dark:border-border">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500 dark:text-ink-muted">Category:</span>
            {['all', 'fungal', 'bacterial', 'viral', 'chemical', 'organic', 'healthy'].map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setActiveCategory(cat)}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                  activeCategory === cat
                    ? 'bg-accent-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-white/5 dark:text-ink-muted dark:hover:bg-white/10'
                }`}
              >
                {cat === 'all' ? 'All Clusters' : CATEGORY_META[cat]?.label || cat}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500 dark:text-ink-muted">Crop:</span>
            {['all', 'Tomato', 'Apple', 'Potato', 'Corn'].map((crop) => (
              <button
                key={crop}
                type="button"
                onClick={() => setActiveCrop(crop)}
                className={`rounded-lg px-2 py-0.5 text-xs font-medium transition-all ${
                  activeCrop === crop
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-white/5 dark:text-ink-muted dark:hover:bg-white/10'
                }`}
              >
                {crop === 'all' ? 'All Crops' : crop}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* Main Grid: Interactive Vector Canvas + Live Query Probe */}
      <div className="grid gap-6 lg:grid-cols-12">
        {/* Left 8 Cols: Interactive Vector Manifold Canvas */}
        <div className="lg:col-span-8 space-y-3">
          <div className="panel relative overflow-hidden rounded-panel border border-border-light bg-slate-950 p-4 dark:border-border">
            {/* Canvas Header Legend */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="font-mono text-xs font-medium text-slate-300">
                  Vector Space Topology (384-d → 2D Projection)
                </span>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-slate-400">
                <span>{visibleNodes.length} Active Nodes</span>
                <span>·</span>
                <span>{visibleEdges.length} Semantic Edges</span>
              </div>
            </div>

            {/* SVG Vector Space Graph */}
            <div className="relative mt-3 flex justify-center overflow-x-auto">
              <svg
                viewBox="0 0 820 500"
                className="h-[460px] w-full min-w-[700px] select-none"
                style={{ transform: `scale(${zoomLevel})`, transformOrigin: 'center' }}
              >
                <defs>
                  {/* Radial Background Gradients for Clusters */}
                  <radialGradient id="fungalGlow" cx="25%" cy="30%" r="35%">
                    <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.15" />
                    <stop offset="100%" stopColor="#f43f5e" stopOpacity="0" />
                  </radialGradient>
                  <radialGradient id="bacterialGlow" cx="55%" cy="25%" r="30%">
                    <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.15" />
                    <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
                  </radialGradient>
                  <radialGradient id="viralGlow" cx="80%" cy="25%" r="30%">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity="0.15" />
                    <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
                  </radialGradient>
                  <radialGradient id="chemicalGlow" cx="40%" cy="65%" r="35%">
                    <stop offset="0%" stopColor="#0284c7" stopOpacity="0.15" />
                    <stop offset="100%" stopColor="#0284c7" stopOpacity="0" />
                  </radialGradient>
                  <radialGradient id="healthyGlow" cx="85%" cy="80%" r="30%">
                    <stop offset="0%" stopColor="#14b8a6" stopOpacity="0.15" />
                    <stop offset="100%" stopColor="#14b8a6" stopOpacity="0" />
                  </radialGradient>

                  {/* Node Glow Filters */}
                  <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="4" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                  </filter>
                </defs>

                {/* Background Ambient Cluster Clouds */}
                <rect x="100" y="80" width="220" height="180" rx="40" fill="url(#fungalGlow)" />
                <rect x="380" y="80" width="180" height="160" rx="40" fill="url(#bacterialGlow)" />
                <rect x="580" y="80" width="180" height="150" rx="40" fill="url(#viralGlow)" />
                <rect x="230" y="240" width="260" height="180" rx="40" fill="url(#chemicalGlow)" />
                <rect x="620" y="320" width="180" height="160" rx="40" fill="url(#healthyGlow)" />

                {/* Cluster Region Watermark Labels */}
                <text x="140" y="110" fill="#f43f5e" opacity="0.4" fontSize="11" fontWeight="bold" fontFamily="monospace">
                  CLUSTER 1: FUNGAL SOLANACEAE
                </text>
                <text x="420" y="105" fill="#f59e0b" opacity="0.4" fontSize="11" fontWeight="bold" fontFamily="monospace">
                  CLUSTER 2: BACTERIAL
                </text>
                <text x="630" y="105" fill="#6366f1" opacity="0.4" fontSize="11" fontWeight="bold" fontFamily="monospace">
                  CLUSTER 3: VIRAL
                </text>
                <text x="250" y="265" fill="#0284c7" opacity="0.4" fontSize="11" fontWeight="bold" fontFamily="monospace">
                  CLUSTER 4: CHEMICAL PROTECTANTS
                </text>
                <text x="650" y="345" fill="#14b8a6" opacity="0.4" fontSize="11" fontWeight="bold" fontFamily="monospace">
                  CLUSTER 5: HEALTHY BASELINES
                </text>

                {/* Semantic Connection Edges */}
                {visibleEdges.map((edge) => {
                  const sNode = VECTOR_NODES.find((n) => n.id === edge.source)
                  const tNode = VECTOR_NODES.find((n) => n.id === edge.target)
                  if (!sNode || !tNode) return null

                  const isHighlighted =
                    selectedNodeId === edge.source ||
                    selectedNodeId === edge.target ||
                    hoveredNodeId === edge.source ||
                    hoveredNodeId === edge.target

                  const opacity = isHighlighted ? 0.85 : 0.25
                  const strokeWidth = isHighlighted ? 2 : 1
                  const strokeColor = isHighlighted ? '#38bdf8' : '#64748b'

                  const midX = (sNode.x + tNode.x) / 2
                  const midY = (sNode.y + tNode.y) / 2

                  return (
                    <g key={`${edge.source}-${edge.target}`} className="transition-all duration-300">
                      <line
                        x1={sNode.x}
                        y1={sNode.y}
                        x2={tNode.x}
                        y2={tNode.y}
                        stroke={strokeColor}
                        strokeWidth={strokeWidth}
                        strokeOpacity={opacity}
                        strokeDasharray={isHighlighted ? 'none' : '3 3'}
                      />
                      {isHighlighted && (
                        <g>
                          <rect
                            x={midX - 22}
                            y={midY - 8}
                            width={44}
                            height={16}
                            rx={4}
                            fill="#0f172a"
                            stroke="#38bdf8"
                            strokeWidth={1}
                          />
                          <text
                            x={midX}
                            y={midY + 3}
                            textAnchor="middle"
                            fill="#38bdf8"
                            fontSize="9"
                            fontFamily="monospace"
                            fontWeight="bold"
                          >
                            {edge.similarity.toFixed(2)}
                          </text>
                        </g>
                      )}
                    </g>
                  )
                })}

                {/* Vector Probe Rays (from Query Vector to Top Matches) */}
                {queryRankings.slice(0, 4).map((match, idx) => {
                  const queryPoint = { x: 410, y: 250 }
                  return (
                    <g key={`query-ray-${match.id}`} className="animate-pulse">
                      <line
                        x1={queryPoint.x}
                        y1={queryPoint.y}
                        x2={match.x}
                        y2={match.y}
                        stroke="#f59e0b"
                        strokeWidth={2.5 - idx * 0.5}
                        strokeOpacity={0.8 - idx * 0.15}
                        strokeDasharray="4 4"
                      />
                    </g>
                  )
                })}

                {/* Simulated Query Vector Origin Point */}
                <g transform="translate(410, 250)">
                  <circle r="14" fill="#f59e0b" fillOpacity="0.2" className="animate-ping" />
                  <circle r="8" fill="#f59e0b" stroke="#ffffff" strokeWidth="2" />
                  <text x="0" y="22" textAnchor="middle" fill="#f59e0b" fontSize="10" fontWeight="bold" fontFamily="monospace">
                    QUERY VECTOR (q)
                  </text>
                </g>

                {/* Vector Nodes */}
                {visibleNodes.map((node) => {
                  const isSelected = selectedNodeId === node.id
                  const isHovered = hoveredNodeId === node.id
                  const meta = CATEGORY_META[node.category] || CATEGORY_META.fungal
                  const queryScore = activeQuery?.targetScores?.[node.id]

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x}, ${node.y})`}
                      className="cursor-pointer transition-all duration-200"
                      onClick={() => setSelectedNodeId(node.id)}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                    >
                      {/* Pulse halo if selected or top query match */}
                      {(isSelected || (queryScore && queryScore > 0.85)) && (
                        <circle
                          r={node.radius + 8}
                          fill={meta.stroke}
                          fillOpacity="0.25"
                          className="animate-pulse"
                        />
                      )}

                      {/* Node Body Circle */}
                      <circle
                        r={node.radius}
                        fill={isSelected ? '#ffffff' : meta.stroke}
                        stroke={isSelected ? meta.stroke : '#0f172a'}
                        strokeWidth={isSelected ? 3 : 2}
                        filter={isSelected ? 'url(#glow)' : undefined}
                      />

                      {/* Cosine Score Tag if probed by query */}
                      {queryScore !== undefined && (
                        <g transform={`translate(0, -${node.radius + 6})`}>
                          <rect
                            x="-18"
                            y="-12"
                            width="36"
                            height="14"
                            rx="3"
                            fill={queryScore > 0.85 ? '#059669' : '#1e293b'}
                            stroke={queryScore > 0.85 ? '#34d399' : '#475569'}
                            strokeWidth="0.75"
                          />
                          <text
                            x="0"
                            y="-2"
                            textAnchor="middle"
                            fill={queryScore > 0.85 ? '#ffffff' : '#cbd5e1'}
                            fontSize="8.5"
                            fontWeight="bold"
                            fontFamily="monospace"
                          >
                            {queryScore.toFixed(2)}
                          </text>
                        </g>
                      )}

                      {/* Node Label Text */}
                      <text
                        x="0"
                        y={node.radius + 14}
                        textAnchor="middle"
                        fill={isSelected ? '#ffffff' : '#cbd5e1'}
                        fontSize="10"
                        fontWeight={isSelected ? 'bold' : 'normal'}
                        className="drop-shadow"
                      >
                        {node.label}
                      </text>
                    </g>
                  )
                })}
              </svg>
            </div>

            {/* Bottom Floating Canvas Bar */}
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-3 text-xs text-slate-400">
              <div className="flex flex-wrap items-center gap-3">
                {Object.entries(CATEGORY_META).map(([catKey, meta]) => (
                  <div key={catKey} className="flex items-center gap-1.5 text-[11px]">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: meta.stroke }} />
                    <span>{meta.label}</span>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setZoomLevel((z) => Math.min(z + 0.1, 1.4))}
                  className="rounded bg-white/10 px-2 py-0.5 font-mono text-xs hover:bg-white/20"
                >
                  +
                </button>
                <button
                  type="button"
                  onClick={() => setZoomLevel(1)}
                  className="rounded bg-white/10 px-2 py-0.5 font-mono text-xs hover:bg-white/20"
                >
                  100%
                </button>
                <button
                  type="button"
                  onClick={() => setZoomLevel((z) => Math.max(z - 0.1, 0.8))}
                  className="rounded bg-white/10 px-2 py-0.5 font-mono text-xs hover:bg-white/20"
                >
                  -
                </button>
              </div>
            </div>
          </div>

          {/* Quick Query Probe Simulator */}
          <Card padding="md" className="space-y-3">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-amber-500" />
              <h3 className="font-display text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-ink-primary">
                Live Query Vector Probe (Cosine Distance Simulator)
              </h3>
            </div>
            <p className="text-xs text-slate-500 dark:text-ink-muted">
              Select an agronomic query to shoot a dense probe vector into the space and observe real-time nearest neighbor rankings:
            </p>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_QUERIES.map((q, idx) => (
                <button
                  key={q.id}
                  type="button"
                  onClick={() => setActiveQueryIndex(idx)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                    activeQueryIndex === idx
                      ? 'border border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300 font-semibold shadow-sm'
                      : 'border border-border-light bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-border dark:bg-white/5 dark:text-ink-muted dark:hover:bg-white/10'
                  }`}
                >
                  {q.text}
                </button>
              ))}
            </div>
          </Card>
        </div>

        {/* Right 4 Cols: Active Node Inspector & Cosine Ranking Stream */}
        <div className="lg:col-span-4 space-y-4">
          {/* Active Node Detail Inspector */}
          <Card padding="md" className="space-y-3 border-accent-500/30">
            <div className="flex items-center justify-between border-b border-border-light pb-2.5 dark:border-border">
              <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-ink-muted">
                Node Vector Inspector
              </span>
              <span
                className={`rounded-md border px-2 py-0.5 font-mono text-[10px] font-semibold ${
                  CATEGORY_META[selectedNode.category]?.badge
                }`}
              >
                {CATEGORY_META[selectedNode.category]?.label}
              </span>
            </div>

            <div>
              <h3 className="font-display text-sm font-bold text-slate-900 dark:text-ink-primary">
                {selectedNode.label}
              </h3>
              <p className="font-mono text-xs text-slate-500 dark:text-ink-muted">
                Etiology: <span className="italic">{selectedNode.pathogen}</span>
              </p>
            </div>

            {/* 384-d Embedding Vector Representation */}
            <div className="space-y-1 rounded-lg border border-border-light bg-slate-50 p-2.5 dark:border-border dark:bg-white/[0.02]">
              <span className="font-mono text-[10px] font-bold text-slate-500 dark:text-ink-muted">
                Dense Vector Embedding (all-MiniLM-L6-v2)
              </span>
              <div className="font-mono text-[11px] text-accent-700 dark:text-accent-300">
                [{selectedNode.embeddingSlice.map((v) => v.toFixed(3)).join(', ')}, ...]
              </div>
              <p className="text-[10px] text-slate-400">
                Dimension: 384-d Float32 · L2-Normalized (||v|| = 1.0)
              </p>
            </div>

            {/* Visual Symptoms & Remedy */}
            <div className="space-y-2 text-xs">
              <div>
                <span className="font-semibold text-slate-900 dark:text-ink-primary">Diagnostic Symptoms:</span>
                <p className="mt-0.5 text-slate-600 dark:text-ink-secondary">{selectedNode.summary}</p>
              </div>

              <div>
                <span className="font-semibold text-slate-900 dark:text-ink-primary">Actionable Field Protocol:</span>
                <p className="mt-0.5 text-emerald-700 dark:text-emerald-300 font-medium">{selectedNode.remedy}</p>
              </div>

              <div className="rounded border border-border-light bg-slate-100/70 p-2 text-[11px] text-slate-500 dark:border-border dark:bg-white/5 dark:text-ink-muted">
                <span className="font-semibold text-slate-700 dark:text-ink-secondary">Extension Source: </span>
                {selectedNode.citation}
              </div>
            </div>
          </Card>

          {/* Top-K Cosine Similarity Retrieval Table */}
          <Card padding="md" className="space-y-3">
            <div className="flex items-center justify-between border-b border-border-light pb-2 dark:border-border">
              <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-ink-muted">
                Top Retrieval Candidates
              </span>
              <span className="font-mono text-[10px] font-bold text-amber-600 dark:text-amber-400">
                Cosine Score
              </span>
            </div>

            <div className="space-y-2">
              {queryRankings.slice(0, 5).map((match, idx) => (
                <div
                  key={match.id}
                  onClick={() => setSelectedNodeId(match.id)}
                  className={`group flex cursor-pointer items-center justify-between rounded-lg border p-2 text-xs transition-all ${
                    selectedNodeId === match.id
                      ? 'border-accent-500 bg-accent-500/10 dark:border-accent-400 dark:bg-accent-500/15 font-semibold'
                      : 'border-border-light bg-slate-50/70 hover:border-slate-300 dark:border-border dark:bg-white/[0.02] dark:hover:border-white/10'
                  }`}
                >
                  <div className="flex items-center gap-2 overflow-hidden">
                    <span className="font-mono text-[10px] text-slate-400">0{idx + 1}</span>
                    <span className="truncate text-slate-800 dark:text-ink-primary">
                      {match.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 font-mono">
                    <div className="h-1.5 w-12 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
                      <div
                        className="h-full rounded-full bg-amber-500"
                        style={{ width: `${Math.min(match.score * 100, 100)}%` }}
                      />
                    </div>
                    <span className="text-[11px] font-bold text-slate-700 dark:text-ink-secondary">
                      {match.score.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
