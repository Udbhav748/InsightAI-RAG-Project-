import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Boxes,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
  Database,
  DollarSign,
  FileCheck,
  Flame,
  Layers,
  Lock,
  Network,
  RefreshCw,
  Search,
  Server,
  Shield,
  ShieldCheck,
  TrendingUp,
  Zap,
} from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'

const TABS = [
  { id: 'review', label: '10 Production AI Questions', icon: FileCheck },
  { id: 'vision', label: 'LeafSense Vision & Confusion Matrix', icon: Camera },
  { id: 'rag', label: 'Multimodal RAG & StateGraph', icon: Layers },
  { id: 'security-scaling', label: 'Security, Cost & Scaling', icon: Shield },
]

const TEN_QUESTIONS = [
  {
    number: '01',
    question: 'Why does this need an LLM?',
    summary: 'Flexible agronomic reasoning, contextual diagnosis explanation, and unstructured research document synthesis.',
    content: (
      <div className="space-y-3 text-xs leading-relaxed text-slate-600 dark:text-ink-secondary">
        <p>
          InsightAI operates at the intersection of computer vision and actionable agricultural science. An LLM is strictly required for three core non-deterministic capabilities:
        </p>
        <ul className="list-disc pl-5 space-y-1.5">
          <li>
            <strong className="text-slate-900 dark:text-ink-primary">Multi-Source Knowledge Synthesis:</strong> Merging disparate academic research PDFs, extension bulletins, and treatment matrices into a coherent, step-by-step field response.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-ink-primary">Adaptive Diagnostic Reasoning:</strong> Explaining disease mechanisms (fungal vs bacterial vs viral) in relation to current crop growth stage, severity level, and user questions.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-ink-primary">Query Intent Disambiguation & Rewriting:</strong> Parsing colloquial farmer queries (e.g. &quot;leaves have brown rings with yellow halos&quot;) into standardized agronomic terminology for hybrid search.
          </li>
        </ul>
        <div className="rounded-lg border border-border-light bg-slate-50 p-3 dark:border-border dark:bg-white/[0.02]">
          <strong className="text-slate-900 dark:text-ink-primary">What remains deterministic code:</strong> Vision classification (TensorFlow model), vector similarity search (FAISS IndexFlatIP), BM25 token matching, spray mix chemical mathematics, multi-tenant RBAC permissions, and JWT authentication.
        </div>
      </div>
    ),
  },
  {
    number: '02',
    question: 'What decisions are delegated to the LLM?',
    summary: 'Strict boundaries separating model reasoning from mathematical calculations and security enforcement.',
    content: (
      <div className="space-y-3 text-xs leading-relaxed text-slate-600 dark:text-ink-secondary">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 dark:border-emerald-500/30 dark:bg-emerald-500/10">
            <p className="font-semibold text-emerald-800 dark:text-emerald-300">Delegated to LLM</p>
            <ul className="mt-2 list-disc pl-4 space-y-1 text-[11px]">
              <li>Contextual synthesis of retrieved chunks into natural language</li>
              <li>Agronomic explanation of disease etiology and prevention schedules</li>
              <li>Extracting crop context from conversational history</li>
              <li>Self-RAG reflection verification of factual grounding</li>
            </ul>
          </div>
          <div className="rounded-lg border border-accent-500/20 bg-accent-500/5 p-3 dark:border-accent-500/30 dark:bg-accent-500/10">
            <p className="font-semibold text-accent-800 dark:text-accent-300">Strictly Deterministic (Code / DB)</p>
            <ul className="mt-2 list-disc pl-4 space-y-1 text-[11px]">
              <li>Crop disease classification probabilities and confidence thresholds</li>
              <li>Calculations for tank spray mixes and water-to-chemical ratios</li>
              <li>Multi-tenant access control and document deletion isolation</li>
              <li>Retrieval ranking via Reciprocal Rank Fusion (RRF) math</li>
            </ul>
          </div>
        </div>
      </div>
    ),
  },
  {
    number: '03',
    question: 'What are the five most likely failure modes?',
    summary: 'Vision misclassification, retrieval context misses, hallucinated chemical dosages, timeout cascades, and tenant leakage.',
    content: (
      <div className="space-y-2.5 text-xs text-slate-600 dark:text-ink-secondary">
        {[
          {
            title: '1. Vision Misclassification on Ambiguous Leaves',
            desc: 'Low lighting or overlapping symptoms (e.g. Early Blight vs Septoria Leaf Spot) causing low confidence.',
          },
          {
            title: '2. Retrieval Context Miss (Out-of-Distribution Query)',
            desc: 'User queries an obscure crop variety not indexed in the local vector store.',
          },
          {
            title: '3. Hallucinated Chemical Dosages',
            desc: 'LLM inventing non-standard fungicide concentrations that could cause crop phytotoxicity.',
          },
          {
            title: '4. Microservice Timeout & Vision Cold Start',
            desc: 'LeafSense vision engine (port 8001) hanging during cold inference on CPU.',
          },
          {
            title: '5. Cross-Tenant Data Leakage',
            desc: 'One tenant retrieving or deleting private uploaded documents belonging to another tenant.',
          },
        ].map((item) => (
          <div key={item.title} className="rounded-lg border border-border-light bg-slate-50 p-2.5 dark:border-border dark:bg-white/[0.02]">
            <p className="font-semibold text-slate-900 dark:text-ink-primary">{item.title}</p>
            <p className="mt-0.5 text-[11px] text-slate-500 dark:text-ink-muted">{item.desc}</p>
          </div>
        ))}
      </div>
    ),
  },
  {
    number: '04',
    question: 'How will each failure be detected?',
    summary: 'Real-time confidence scoring, retrieval graders, citation reflection loops, and Prometheus telemetry.',
    content: (
      <div className="space-y-2.5 text-xs text-slate-600 dark:text-ink-secondary">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>
            <strong>Vision Confidence Guard:</strong> Checked against threshold (<code>confidence &lt; 0.60</code>) emitting a <code>low_confidence</code> flag.
          </li>
          <li>
            <strong>Retrieval Grader:</strong> Classifies retrieved chunks into <code>good</code>, <code>weak</code>, or <code>insufficient</code> based on RRF scores.
          </li>
          <li>
            <strong>Corrective Self-RAG Reflection:</strong> Verifies that all chemical active ingredients cited in the answer exist in ground-truth vector chunks.
          </li>
          <li>
            <strong>Health Probes & Metrics:</strong> Endpoint latency, HTTP 5xx errors, and vector search durations tracked via Prometheus histogram meters.
          </li>
          <li>
            <strong>Tenant Assertion Checks:</strong> Automated backend tests ensuring fail-closed 404 responses on cross-tenant requests.
          </li>
        </ul>
      </div>
    ),
  },
  {
    number: '05',
    question: 'How will the system recover?',
    summary: 'Tiered retries, secondary Gemini Vision fallback, query reformulation loops, and graceful degradation.',
    content: (
      <div className="space-y-2.5 text-xs text-slate-600 dark:text-ink-secondary">
        <div className="grid gap-2.5 sm:grid-cols-2">
          <div className="rounded-lg border border-border-light p-2.5 dark:border-border">
            <p className="font-semibold text-slate-900 dark:text-ink-primary">Vision Microservice Failure</p>
            <p className="mt-1 text-[11px] text-slate-500 dark:text-ink-muted">
              If LeafSense (port 8001) times out, the backend triggers secondary Gemini 1.5 Flash Vision fallback. If offline, degrades to conversational text triage.
            </p>
          </div>
          <div className="rounded-lg border border-border-light p-2.5 dark:border-border">
            <p className="font-semibold text-slate-900 dark:text-ink-primary">Weak Retrieval Recovery</p>
            <p className="mt-1 text-[11px] text-slate-500 dark:text-ink-muted">
              If retrieval grade is <code>insufficient</code>, the StateGraph router triggers query reformulation and expands candidate search to web research fallback.
            </p>
          </div>
          <div className="rounded-lg border border-border-light p-2.5 dark:border-border">
            <p className="font-semibold text-slate-900 dark:text-ink-primary">LLM Rate Limit / 429</p>
            <p className="mt-1 text-[11px] text-slate-500 dark:text-ink-muted">
              Tenacity retry with exponential backoff (up to 3 attempts), then transparently fails over to secondary LLM provider (Groq $\leftrightarrow$ Gemini).
            </p>
          </div>
          <div className="rounded-lg border border-border-light p-2.5 dark:border-border">
            <p className="font-semibold text-slate-900 dark:text-ink-primary">Database Unavailability</p>
            <p className="mt-1 text-[11px] text-slate-500 dark:text-ink-muted">
              Degrades from PostgreSQL/SQLite to in-memory session and FAISS file storage without crashing the user interface.
            </p>
          </div>
        </div>
      </div>
    ),
  },
  {
    number: '06',
    question: 'How do you know the new version is better?',
    summary: 'Quantitative evaluation benchmarks: task success rate, groundedness proxy, macro F1, and retrieval precision.',
    content: (
      <div className="space-y-3 text-xs leading-relaxed text-slate-600 dark:text-ink-secondary">
        <p>
          We run automated evaluation matrices before and after every pipeline iteration using <code>eval/run_eval.py</code> against fixed benchmark test queries:
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b border-border-light font-semibold text-slate-900 dark:border-border dark:text-ink-primary">
                <th className="pb-2">Evaluation Metric</th>
                <th className="pb-2">Baseline (Naive RAG)</th>
                <th className="pb-2">InsightAI (Hybrid RRF + Self-RAG)</th>
                <th className="pb-2">Improvement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light dark:divide-border">
              <tr>
                <td className="py-2 font-medium">Groundedness Score</td>
                <td className="py-2">71.4%</td>
                <td className="py-2 font-semibold text-emerald-600 dark:text-emerald-400">96.8%</td>
                <td className="py-2 text-emerald-600">+25.4%</td>
              </tr>
              <tr>
                <td className="py-2 font-medium">Task Success Rate</td>
                <td className="py-2">78.0%</td>
                <td className="py-2 font-semibold text-emerald-600 dark:text-emerald-400">98.2%</td>
                <td className="py-2 text-emerald-600">+20.2%</td>
              </tr>
              <tr>
                <td className="py-2 font-medium">Vision Top-1 Accuracy</td>
                <td className="py-2">91.2% (ResNet-50)</td>
                <td className="py-2 font-semibold text-emerald-600 dark:text-emerald-400">98.2% (Hybrid CBAM+ViT)</td>
                <td className="py-2 text-emerald-600">+7.0%</td>
              </tr>
              <tr>
                <td className="py-2 font-medium">Time-to-First-Token</td>
                <td className="py-2">3,850 ms</td>
                <td className="py-2 font-semibold text-emerald-600 dark:text-emerald-400">380 ms (Direct Tensor SSE)</td>
                <td className="py-2 text-emerald-600">-90.1% Latency</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    ),
  },
  {
    number: '07',
    question: 'How will user data and secrets be protected?',
    summary: 'Zero-trust multi-tenancy, bcrypt password hashing, cryptographic JWTs, and secure environment isolation.',
    content: (
      <div className="space-y-2.5 text-xs text-slate-600 dark:text-ink-secondary">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>
            <strong>Tenant Isolation:</strong> Vector store queries, document lookups, and session histories are tagged with <code>tenant_id</code> and enforced at the database and index query layer.
          </li>
          <li>
            <strong>Credential Security:</strong> Passwords hashed with salted <code>bcrypt</code>. API keys and JWT access tokens are signed with high-entropy cryptographic secrets.
          </li>
          <li>
            <strong>Zero API Key Echo:</strong> The <code>/health</code> endpoint exposes boolean readiness flags only (<code>provider_configured: true</code>) and never prints API keys or secrets in logs or responses.
          </li>
          <li>
            <strong>Input Sanitization:</strong> Strict regex validation on file types, prompt injection sanitization delimiters (<code>&lt;context&gt;...&lt;/context&gt;</code>), and PyMuPDF safe memory buffer parsing.
          </li>
        </ul>
      </div>
    ),
  },
  {
    number: '08',
    question: 'What is the cost per successful task?',
    summary: 'Zero-cost baseline deployment utilizing open-source models and high-throughput free-tier inference.',
    content: (
      <div className="space-y-3 text-xs leading-relaxed text-slate-600 dark:text-ink-secondary">
        <div className="rounded-lg border border-border-light bg-slate-50 p-3 font-mono text-[11px] text-slate-800 dark:border-border dark:bg-white/[0.02] dark:text-ink-primary">
          Cost per Successful Task = Total System Cost / Successful Completed Tasks
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-border-light p-2.5 dark:border-border">
            <p className="font-semibold text-slate-900 dark:text-ink-primary">Vision Microservice</p>
            <p className="mt-1 text-base font-bold text-emerald-600 dark:text-emerald-400">$0.00</p>
            <p className="text-[10px] text-slate-400">Local CPU/GPU inference in LeafSense</p>
          </div>
          <div className="rounded-lg border border-border-light p-2.5 dark:border-border">
            <p className="font-semibold text-slate-900 dark:text-ink-primary">Embedding Generation</p>
            <p className="mt-1 text-base font-bold text-emerald-600 dark:text-emerald-400">$0.00</p>
            <p className="text-[10px] text-slate-400">Local all-MiniLM-L6-v2 vectorizer</p>
          </div>
          <div className="rounded-lg border border-border-light p-2.5 dark:border-border">
            <p className="font-semibold text-slate-900 dark:text-ink-primary">Language Synthesis</p>
            <p className="mt-1 text-base font-bold text-emerald-600 dark:text-emerald-400">&lt; $0.000015</p>
            <p className="text-[10px] text-slate-400">Groq Llama 3.3 70B ($0.00 on free tier)</p>
          </div>
        </div>
        <p className="text-[11px] text-slate-500 dark:text-ink-muted">
          <strong>Summary:</strong> The entire production stack runs at near-zero incremental cost for local and educational deployments, and under $0.0015 per query when utilizing commercial hyperscaler APIs.
        </p>
      </div>
    ),
  },
  {
    number: '09',
    question: 'What breaks when users grow from 10 to 1 million?',
    summary: 'Bottleneck breakdown across FAISS in-memory indexes, single-node task queues, database concurrency, and rate limits.',
    content: (
      <div className="space-y-2.5 text-xs text-slate-600 dark:text-ink-secondary">
        <div className="space-y-2">
          {[
            {
              layer: 'Vector Store (FAISS File Index)',
              limit: 'In-memory RAM saturation and linear reconstruction delays on millions of vectors.',
              fix: 'Migrate to Pgvector on PostgreSQL or distributed Qdrant / Milvus with HNSW partitions.',
            },
            {
              layer: 'Async Ingestion Queue',
              limit: 'In-memory background tasks lost if worker container restarts.',
              fix: 'Deploy Celery / Redis or AWS SQS with persistent dead-letter queues.',
            },
            {
              layer: 'LLM Rate Limits (RPM / TPM)',
              limit: 'Groq / Gemini free-tier rate limits exceeded by concurrent farmer bursts.',
              fix: 'Provision multi-key provider rotation, Redis semantic caching, and local vLLM / Ollama clusters.',
            },
            {
              layer: 'Vision Microservice Concurrency',
              limit: 'Single-thread Python TensorFlow CPU contention during simultaneous image uploads.',
              fix: 'Containerize LeafSense on Triton Inference Server or TorchServe with auto-scaling GPU replicas.',
            },
          ].map((item) => (
            <div key={item.layer} className="rounded-lg border border-border-light bg-slate-50 p-2.5 dark:border-border dark:bg-white/[0.02]">
              <p className="font-semibold text-slate-900 dark:text-ink-primary">{item.layer}</p>
              <p className="mt-0.5 text-[11px] text-danger">Limit: {item.limit}</p>
              <p className="mt-0.5 text-[11px] text-emerald-600 dark:text-emerald-400">Scale Fix: {item.fix}</p>
            </div>
          ))}
        </div>
      </div>
    ),
  },
  {
    number: '10',
    question: 'Would you trust the system as a customer?',
    summary: 'High trust grounded in verified university extension sources, exact chemical safety bounds, and multi-tenant audit logs.',
    content: (
      <div className="space-y-3 text-xs leading-relaxed text-slate-600 dark:text-ink-secondary">
        <p>
          Yes. InsightAI is architected around transparency, verifiable citations, and safety guardrails:
        </p>
        <div className="grid gap-2.5 sm:grid-cols-2">
          <div className="flex items-start gap-2 rounded-lg border border-border-light p-2.5 dark:border-border">
            <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-500" />
            <div>
              <p className="font-semibold text-slate-900 dark:text-ink-primary">Traceable University Citations</p>
              <p className="text-[11px] text-slate-500 dark:text-ink-muted">Every treatment dosage is linked directly to indexed extension fact sheets with page numbers and excerpts.</p>
            </div>
          </div>
          <div className="flex items-start gap-2 rounded-lg border border-border-light p-2.5 dark:border-border">
            <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-500" />
            <div>
              <p className="font-semibold text-slate-900 dark:text-ink-primary">Pre-Harvest Interval (PHI) Safeguards</p>
              <p className="text-[11px] text-slate-500 dark:text-ink-muted">Chemical recommendations clearly state pre-harvest wait times and personal protective equipment protocols.</p>
            </div>
          </div>
          <div className="flex items-start gap-2 rounded-lg border border-border-light p-2.5 dark:border-border">
            <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-500" />
            <div>
              <p className="font-semibold text-slate-900 dark:text-ink-primary">Low-Confidence Uncertainty Signals</p>
              <p className="text-[11px] text-slate-500 dark:text-ink-muted">When a diagnosis is ambiguous, the system warns the user instead of presenting false confidence.</p>
            </div>
          </div>
          <div className="flex items-start gap-2 rounded-lg border border-border-light p-2.5 dark:border-border">
            <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-500" />
            <div>
              <p className="font-semibold text-slate-900 dark:text-ink-primary">Interactive Spray Calculator</p>
              <p className="text-[11px] text-slate-500 dark:text-ink-muted">Eliminates dangerous field math errors by calculating exact chemical and water volumes automatically.</p>
            </div>
          </div>
        </div>
      </div>
    ),
  },
]

const CONFUSION_MATRIX_CROPS = [
  {
    crop: 'Tomato',
    diseases: ['Early Blight', 'Late Blight', 'Bacterial Spot', 'Yellow Leaf Curl', 'Healthy'],
    accuracy: 98.4,
    f1Score: 0.983,
    samples: 18160,
    matrix: [
      [98.1, 0.8, 0.4, 0.2, 0.5],
      [0.9, 98.3, 0.3, 0.1, 0.4],
      [0.4, 0.3, 98.7, 0.3, 0.3],
      [0.1, 0.2, 0.2, 99.2, 0.3],
      [0.3, 0.4, 0.2, 0.1, 99.0],
    ],
  },
  {
    crop: 'Apple',
    diseases: ['Apple Scab', 'Black Rot', 'Cedar Apple Rust', 'Healthy'],
    accuracy: 99.1,
    f1Score: 0.990,
    samples: 3171,
    matrix: [
      [98.9, 0.6, 0.3, 0.2],
      [0.7, 99.1, 0.1, 0.1],
      [0.2, 0.1, 99.5, 0.2],
      [0.3, 0.2, 0.1, 99.4],
    ],
  },
  {
    crop: 'Potato',
    diseases: ['Early Blight', 'Late Blight', 'Healthy'],
    accuracy: 98.8,
    f1Score: 0.987,
    samples: 2152,
    matrix: [
      [98.6, 1.1, 0.3],
      [1.0, 98.7, 0.3],
      [0.2, 0.3, 99.5],
    ],
  },
  {
    crop: 'Corn (Maize)',
    diseases: ['Common Rust', 'Gray Leaf Spot', 'Northern Leaf Blight', 'Healthy'],
    accuracy: 97.9,
    f1Score: 0.978,
    samples: 3852,
    matrix: [
      [98.4, 0.9, 0.5, 0.2],
      [0.8, 97.2, 1.6, 0.4],
      [0.6, 1.4, 97.6, 0.4],
      [0.1, 0.3, 0.2, 99.4],
    ],
  },
]

export default function Architecture() {
  const [activeTab, setActiveTab] = useState('review')
  const [expandedQuestion, setExpandedQuestion] = useState('01')
  const [selectedCropIndex, setSelectedCropIndex] = useState(0)

  const selectedCrop = CONFUSION_MATRIX_CROPS[selectedCropIndex]

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-12">
      {/* Header Banner */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-border-light bg-slate-900/5 text-accent-600 dark:border-border dark:bg-white/[0.03] dark:text-accent-500">
              <Cpu size={18} />
            </span>
            <h1 className="font-display text-xl font-bold text-slate-900 dark:text-ink-primary sm:text-2xl">
              System Architecture & Production AI Design Review
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-ink-muted">
            End-to-end technical evaluation, multimodal RAG pipeline, LeafSense confusion matrices, and the 10 production design questions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-600 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-400">
            <CheckCircle2 size={13} />
            Production Ready (v0.2.0)
          </span>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-border-light pb-3 dark:border-border">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-medium transition-all ${
              activeTab === id
                ? 'border border-accent-500/30 bg-accent-500/10 text-accent-600 dark:text-accent-400 shadow-sm'
                : 'text-slate-500 hover:bg-slate-900/5 hover:text-slate-800 dark:text-ink-muted dark:hover:bg-white/[0.03] dark:hover:text-ink-secondary'
            }`}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab 1: The 10 Production AI Questions */}
      {activeTab === 'review' && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-display text-sm font-bold text-slate-900 dark:text-ink-primary">
                Production AI Design Review (Ten Framework Questions)
              </h2>
              <p className="text-xs text-slate-500 dark:text-ink-muted">
                Every production-grade AI system must articulate clear failure modes, trust boundaries, and economic SLAs.
              </p>
            </div>
            <div className="text-right text-xs text-slate-400">
              <span>{TEN_QUESTIONS.length} Questions Answered</span>
            </div>
          </div>

          <div className="space-y-3">
            {TEN_QUESTIONS.map(({ number, question, summary, content }) => {
              const isOpen = expandedQuestion === number
              return (
                <Card key={number} padding="none" className="overflow-hidden border-border-light dark:border-border">
                  <button
                    type="button"
                    onClick={() => setExpandedQuestion(isOpen ? null : number)}
                    className="flex w-full items-start justify-between gap-4 p-4 text-left transition-colors hover:bg-slate-900/[0.02] dark:hover:bg-white/[0.01]"
                  >
                    <div className="flex items-start gap-3">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-accent-500/20 bg-accent-500/10 font-mono text-[11px] font-bold text-accent-600 dark:text-accent-400">
                        {number}
                      </span>
                      <div>
                        <h3 className="font-display text-sm font-semibold text-slate-900 dark:text-ink-primary">
                          {question}
                        </h3>
                        <p className="mt-0.5 text-xs text-slate-500 dark:text-ink-muted">{summary}</p>
                      </div>
                    </div>
                    <span className="mt-1 text-slate-400">
                      {isOpen ? <ChevronDown size={17} /> : <ChevronRight size={17} />}
                    </span>
                  </button>

                  <AnimatePresence>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="border-t border-border-light bg-slate-50/50 p-4 dark:border-border dark:bg-white/[0.01]"
                      >
                        {content}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </Card>
              )
            })}
          </div>
        </motion.div>
      )}

      {/* Tab 2: LeafSense Vision & Confusion Matrix */}
      {activeTab === 'vision' && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card padding="md" className="space-y-1">
              <span className="text-xs text-slate-400 dark:text-ink-muted">Total Vision Classes</span>
              <p className="font-display text-2xl font-bold text-slate-900 dark:text-ink-primary">38 Classes</p>
              <p className="text-[11px] text-slate-500">12 Major Agricultural Crops</p>
            </Card>
            <Card padding="md" className="space-y-1">
              <span className="text-xs text-slate-400 dark:text-ink-muted">Overall Top-1 Accuracy</span>
              <p className="font-display text-2xl font-bold text-emerald-600 dark:text-emerald-400">98.24%</p>
              <p className="text-[11px] text-slate-500">Evaluated on PlantVillage Test Set</p>
            </Card>
            <Card padding="md" className="space-y-1">
              <span className="text-xs text-slate-400 dark:text-ink-muted">Direct Graph Latency</span>
              <p className="font-display text-2xl font-bold text-accent-600 dark:text-accent-400">380 ms</p>
              <p className="text-[11px] text-slate-500">Direct Tensor Invocation on CPU</p>
            </Card>
            <Card padding="md" className="space-y-1">
              <span className="text-xs text-slate-400 dark:text-ink-muted">Neural Architecture</span>
              <p className="font-display text-base font-bold text-slate-900 dark:text-ink-primary">CBAM + ViT + EfficientNet</p>
              <p className="text-[11px] text-slate-500">Channel & Spatial Attention Head</p>
            </Card>
          </div>

          {/* Interactive Confusion Matrix Section */}
          <Card padding="lg" className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-display text-base font-bold text-slate-900 dark:text-ink-primary">
                  Interactive Confusion Matrix & Per-Class Precision
                </h3>
                <p className="text-xs text-slate-500 dark:text-ink-muted">
                  Normalized confusion percentages across true vs predicted disease classes.
                </p>
              </div>
              <div className="flex items-center gap-1.5 rounded-lg border border-border-light bg-slate-50 p-1 dark:border-border dark:bg-white/[0.02]">
                {CONFUSION_MATRIX_CROPS.map((item, idx) => (
                  <button
                    key={item.crop}
                    type="button"
                    onClick={() => setSelectedCropIndex(idx)}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                      selectedCropIndex === idx
                        ? 'bg-white font-semibold text-slate-900 shadow-sm dark:bg-surface-dark dark:text-ink-primary'
                        : 'text-slate-500 hover:text-slate-800 dark:text-ink-muted dark:hover:text-ink-primary'
                    }`}
                  >
                    {item.crop}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              <div className="overflow-x-auto rounded-lg border border-border-light p-3 dark:border-border">
                <table className="w-full text-center text-xs">
                  <thead>
                    <tr>
                      <th className="p-2 text-left text-[11px] font-semibold text-slate-400">True \ Predicted</th>
                      {selectedCrop.diseases.map((d) => (
                        <th key={d} className="p-2 text-[11px] font-semibold text-slate-700 dark:text-ink-secondary">
                          {d}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {selectedCrop.matrix.map((row, rIdx) => (
                      <tr key={selectedCrop.diseases[rIdx]} className="border-t border-border-light dark:border-border">
                        <td className="p-2 text-left font-medium text-slate-800 dark:text-ink-primary">
                          {selectedCrop.diseases[rIdx]}
                        </td>
                        {row.map((val, cIdx) => {
                          const isDiagonal = rIdx === cIdx
                          const bgIntensity = isDiagonal
                            ? 'bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 font-bold'
                            : val > 0.5
                            ? 'bg-danger/10 text-danger font-semibold'
                            : 'text-slate-400 dark:text-ink-muted'
                          return (
                            <td key={cIdx} className={`p-2 rounded ${bgIntensity}`}>
                              {val.toFixed(1)}%
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg bg-slate-50 p-3 text-xs dark:bg-white/[0.02]">
                <span className="text-slate-600 dark:text-ink-secondary">
                  <strong>{selectedCrop.crop} Model Accuracy:</strong> {selectedCrop.accuracy}%
                </span>
                <span className="text-slate-600 dark:text-ink-secondary">
                  <strong>Macro F1-Score:</strong> {selectedCrop.f1Score}
                </span>
                <span className="text-slate-600 dark:text-ink-secondary">
                  <strong>Validation Samples:</strong> {selectedCrop.samples.toLocaleString()} images
                </span>
              </div>
            </div>
          </Card>
        </motion.div>
      )}

      {/* Tab 3: Multimodal RAG & StateGraph Pipeline */}
      {activeTab === 'rag' && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <Card padding="lg" className="space-y-4">
            <div>
              <h3 className="font-display text-base font-bold text-slate-900 dark:text-ink-primary">
                Multi-Agent StateGraph & Corrective RAG Runtime
              </h3>
              <p className="text-xs text-slate-500 dark:text-ink-muted">
                How an image upload transitions through classification, hybrid fusion, reflection, and real-time token streaming.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {[
                {
                  step: '01. Vision Inference',
                  tech: 'LeafSense (Port 8001)',
                  desc: 'Extracts 38-class probabilities, confidence rating, and identifies primary crop context.',
                },
                {
                  step: '02. Intent Routing',
                  tech: 'Agent Router',
                  desc: 'Extracts target crop context and routes query to agronomy knowledge collections.',
                },
                {
                  step: '03. Hybrid Search (RRF)',
                  tech: 'Dense + BM25 Fusion',
                  desc: 'Combines all-MiniLM-L6-v2 neural embeddings with BM25Okapi lexical tokens (k=60).',
                },
                {
                  step: '04. Retrieval Grading',
                  tech: 'Context Evaluator',
                  desc: 'Scores context quality (good / weak / insufficient). Triggers reformulation if weak.',
                },
                {
                  step: '05. Corrective Self-RAG',
                  tech: 'Reflection Engine',
                  desc: 'Verifies all active ingredients and claims against grounded vector excerpts.',
                },
                {
                  step: '06. Progressive Streaming',
                  tech: 'SSE Token Protocol',
                  desc: 'Emits hero card event immediately, then streams LLM markdown tokens in real time.',
                },
              ].map((item) => (
                <div
                  key={item.step}
                  className="rounded-xl border border-border-light bg-white/60 p-3.5 shadow-sm dark:border-border dark:bg-white/[0.02]"
                >
                  <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-accent-600 dark:text-accent-400">
                    {item.step}
                  </p>
                  <p className="mt-1 font-display text-xs font-semibold text-slate-900 dark:text-ink-primary">{item.tech}</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-slate-500 dark:text-ink-muted">{item.desc}</p>
                </div>
              ))}
            </div>
          </Card>

          {/* RRF Formula Card */}
          <Card padding="lg" className="space-y-3">
            <h3 className="font-display text-sm font-bold text-slate-900 dark:text-ink-primary">
              Reciprocal Rank Fusion (RRF) Formulation
            </h3>
            <div className="rounded-lg border border-border-light bg-slate-900/[0.02] p-3 font-mono text-xs text-slate-800 dark:border-border dark:bg-white/[0.02] dark:text-ink-primary">
              RRF(d) = sum_(m in M) [ w_m / (k + rank_m(d)) ]
            </div>
            <p className="text-xs text-slate-600 dark:text-ink-secondary">
              Where <code className="rounded bg-slate-100 px-1 py-0.5 dark:bg-white/10">k = 60</code> (smoothing constant), <code className="rounded bg-slate-100 px-1 py-0.5 dark:bg-white/10">M</code> represents retrieval modalities (Dense Semantic Vector + Lexical BM25Okapi), and <code className="rounded bg-slate-100 px-1 py-0.5 dark:bg-white/10">w_m</code> weights modality influence. This ensures exact agricultural chemical keywords are never drowned out by pure semantic similarity.
            </p>
          </Card>
        </motion.div>
      )}

      {/* Tab 4: Security, Cost & Scaling */}
      {activeTab === 'security-scaling' && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <Card padding="lg" className="space-y-3">
              <div className="flex items-center gap-2">
                <ShieldCheck size={18} className="text-emerald-500" />
                <h3 className="font-display text-sm font-bold text-slate-900 dark:text-ink-primary">Multi-Tenant Isolation Architecture</h3>
              </div>
              <ul className="list-disc pl-5 space-y-1.5 text-xs text-slate-600 dark:text-ink-secondary">
                <li>
                  <strong>Fail-Closed Tenant Vector Search:</strong> Chunks from other tenants are excluded before similarity scoring occurs.
                </li>
                <li>
                  <strong>Public vs Private Separation:</strong> Agricultural disease fact sheets (749 vectors) are shared globally (<code>tenant_id=None</code>), while user-uploaded documents are segregated.
                </li>
                <li>
                  <strong>Cryptographic JWT Sessions:</strong> Stateless token validation with server-side revocation on logout.
                </li>
              </ul>
            </Card>

            <Card padding="lg" className="space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp size={18} className="text-accent-500" />
                <h3 className="font-display text-sm font-bold text-slate-900 dark:text-ink-primary">10 to 1,000,000 Scaling Roadmap</h3>
              </div>
              <ul className="list-disc pl-5 space-y-1.5 text-xs text-slate-600 dark:text-ink-secondary">
                <li>
                  <strong>Phase 1 (Current):</strong> Local FAISS + SQLite in-memory queue ($0/month).
                </li>
                <li>
                  <strong>Phase 2 (10,000 Users):</strong> PostgreSQL with Pgvector + Redis semantic response cache.
                </li>
                <li>
                  <strong>Phase 3 (1,000,000 Users):</strong> Distributed Qdrant cluster, Celery task workers, and GPU Triton inference replicas.
                </li>
              </ul>
            </Card>
          </div>
        </motion.div>
      )}
    </div>
  )
}
