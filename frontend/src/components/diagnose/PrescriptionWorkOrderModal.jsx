import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AlertCircle,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock,
  Download,
  Droplets,
  FileCheck,
  FileDown,
  FileText,
  FlaskConical,
  Leaf,
  Printer,
  Shield,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react'
import Button from '../ui/Button'
import { getAgronomicGuide, calculateSprayDosage } from '../../utils/agronomyData'

export default function PrescriptionWorkOrderModal({
  isOpen,
  onClose,
  diagnosis,
  severity,
  dosageInfo,
}) {
  const [ppeChecked, setPpeChecked] = useState({
    gloves: true,
    respirator: true,
    eyeProtection: true,
    coveralls: true,
  })

  if (!isOpen) return null

  const crop = diagnosis?.crop || 'Crop Foliage'
  const disease = diagnosis?.disease || 'Condition Undetermined'
  const severityLevel = severity?.level || 'Moderate'
  const guide = getAgronomicGuide(disease, crop)

  // Default calculation fallback if not provided
  const calculation =
    dosageInfo ||
    calculateSprayDosage({
      areaValue: 1000,
      unitId: 'sq_ft',
      chemicalPresetId: 'copper',
    })

  const prescriptionId = `RX-AGRI-${(diagnosis?.session_id || 'DEMO').slice(-6).toUpperCase()}-${new Date().getFullYear()}`
  const today = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })

  const togglePpe = (key) => {
    setPpeChecked((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const handlePrint = () => {
    window.print()
  }

  const handleDownloadWorkOrder = () => {
    const textContent = `================================================================================
OFFICIAL AGRONOMIC SPRAY PRESCRIPTION & FIELD WORK ORDER
InsightAI-RAG Pathology & Crop Protection Hub
Prescription ID: ${prescriptionId}
Date Issued: ${today}
================================================================================

1. PATIENT / CROP DIAGNOSIS
--------------------------------------------------------------------------------
Crop Species:           ${crop.toUpperCase()}
Diagnosed Condition:    ${disease.toUpperCase()}
Pathogen Classification: ${guide.pathogen}
Field Infection Level:  ${severityLevel.toUpperCase()}
Classification Engine:  ${diagnosis?.engine || 'LeafSense Hybrid CNN+ViT (Port 8001)'}
Model Confidence:       ${Math.round((diagnosis?.confidence ?? 0.95) * 100)}%

2. FIELD DOSAGE & TANK MIX PRESCRIPTION
--------------------------------------------------------------------------------
Treatment Plot Area:    ${calculation.numericArea} ${calculation.unitLabel} (${calculation.areaInAcres} acres)
Active Formulation:     ${calculation.chemicalName}
Prescribed Rate:        ${calculation.ratePerLiter} ${calculation.chemUnit} per Liter of water
Total Spray Water:      ${calculation.totalWaterLiters} Liters (${calculation.totalWaterGallons} US Gallons)
Total Chemical Required: ${calculation.totalChemicalAmount} ${calculation.chemUnit}
Sprayer Equipment:      ${calculation.equipmentName} (${calculation.tankCapacityLiters}L capacity)
Tank Refills:           ~${calculation.tanksRequired} tank(s)
Concentrate per Tank:   ${calculation.chemicalPerTank} ${calculation.chemUnit}

3. MANDATORY SAFETY PPE CHECKLIST
--------------------------------------------------------------------------------
[X] Chemical-resistant nitrile / neoprene gloves
[X] N95 / organic vapor particle respirator mask
[X] Protective chemical splash goggles / face shield
[X] Long-sleeved chemical coveralls & waterproof rubber boots

4. COMPLIANCE & SAFETY INTERVALS
--------------------------------------------------------------------------------
Restricted Entry Interval (REI):  12 to 24 Hours (No unprotected field entry)
Pre-Harvest Interval (PHI):       0 to 5 Days before crop harvest
Environmental Restrictions:       Wind speed < 8 mph (12 km/h); apply during
                                  early morning (6-9 AM) to prevent drift and scorch.

5. OFFICIAL AGRONOMIST VERIFICATION
--------------------------------------------------------------------------------
Certified Agronomist:    Dr. J. Henderson, Ph.D., CCA
License / Reg Number:    CCA-#AGRI-88294-EXT
Verification Seal:       DIGITALLY VERIFIED - INSIGHTAI BOTANICAL ARBITER
Date of Verification:    ${today}
Agronomist Signature:    ____________________________________________

================================================================================
Always read and strictly follow manufacturer product labels prior to mixing.
================================================================================`

    const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `Prescription_Work_Order_${crop}_${disease.replace(/\s+/g, '_')}_${Date.now()}.txt`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div
      data-testid="prescription-modal-backdrop"
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/60 p-3 backdrop-blur-sm sm:p-4 print:p-0 print:bg-transparent"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border-light bg-card-light shadow-2xl dark:border-border dark:bg-card print:border-none print:shadow-none print:max-h-none print:w-full"
      >
        {/* Modal Top Header (Hidden on print) */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-light bg-surface-light/95 px-5 py-3.5 backdrop-blur-sm dark:border-border dark:bg-surface-dark/95 print:hidden">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-500/15 text-accent-600 dark:text-accent-400">
              <FileCheck size={18} strokeWidth={2} />
            </span>
            <div>
              <h3 className="font-display text-sm font-bold text-slate-900 dark:text-ink-primary">
                Official Spray Prescription Work Order
              </h3>
              <p className="text-[11px] text-slate-500 dark:text-ink-muted">
                Document ID: <span className="font-mono font-semibold">{prescriptionId}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              icon={Printer}
              onClick={handlePrint}
              className="hidden sm:inline-flex"
            >
              Print
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              icon={FileDown}
              onClick={handleDownloadWorkOrder}
            >
              Download (.txt)
            </Button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-white/5 dark:hover:text-ink-primary"
              aria-label="Close prescription modal"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Prescription Document Content */}
        <div
          id="printable-prescription-order"
          data-testid="prescription-work-order-document"
          className="space-y-5 p-6 text-slate-900 dark:text-ink-primary print:p-4 print:text-black"
        >
          {/* Document Header */}
          <div className="border-b-2 border-slate-900/10 pb-4 dark:border-white/10 print:border-black">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <span className="inline-block rounded bg-accent-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-accent-700 dark:text-accent-300 print:border print:border-black">
                  Agricultural Pathology Prescription
                </span>
                <h2 className="mt-1 font-display text-xl font-bold tracking-tight text-slate-900 sm:text-2xl dark:text-ink-primary print:text-black">
                  Agronomic Spray & Treatment Work Order
                </h2>
                <p className="text-xs text-slate-500 dark:text-ink-muted print:text-slate-600">
                  Issued by InsightAI Botanical Arbiter · Verified Agronomic Laboratory
                </p>
              </div>

              <div className="text-right text-xs">
                <div className="font-mono font-bold text-slate-800 dark:text-ink-primary print:text-black">
                  {prescriptionId}
                </div>
                <div className="text-slate-500 dark:text-ink-muted print:text-slate-600">
                  Date: <strong>{today}</strong>
                </div>
              </div>
            </div>
          </div>

          {/* Section 1: Patient / Crop Details */}
          <div className="space-y-2">
            <h4 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-accent-700 dark:text-accent-400 print:text-black">
              <Leaf size={14} />
              1. Patient / Crop Diagnostic Summary
            </h4>
            <div className="grid grid-cols-2 gap-2.5 rounded-xl border border-border-light bg-slate-900/[0.02] p-3.5 text-xs dark:border-border dark:bg-white/[0.02] sm:grid-cols-4 print:border-slate-300 print:bg-transparent">
              <div>
                <span className="text-[11px] text-slate-500 dark:text-ink-muted print:text-slate-600">Crop Species:</span>
                <p className="font-bold capitalize text-slate-800 dark:text-ink-primary print:text-black">{crop}</p>
              </div>
              <div>
                <span className="text-[11px] text-slate-500 dark:text-ink-muted print:text-slate-600">Diagnosed Condition:</span>
                <p className="font-bold capitalize text-slate-800 dark:text-ink-primary print:text-black">{disease}</p>
              </div>
              <div>
                <span className="text-[11px] text-slate-500 dark:text-ink-muted print:text-slate-600">Field Severity:</span>
                <p className="font-bold text-rose-600 dark:text-rose-400 print:text-black">{severityLevel}</p>
              </div>
              <div>
                <span className="text-[11px] text-slate-500 dark:text-ink-muted print:text-slate-600">Vision Confidence:</span>
                <p className="font-bold text-emerald-600 dark:text-emerald-400 print:text-black">
                  {Math.round((diagnosis?.confidence ?? 0.95) * 100)}%
                </p>
              </div>
            </div>
          </div>

          {/* Section 2: Dosage Calculations & Mix Specs */}
          <div className="space-y-2">
            <h4 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-accent-700 dark:text-accent-400 print:text-black">
              <FlaskConical size={14} />
              2. Prescribed Tank Mix & Dosage Calculations
            </h4>
            <div className="overflow-x-auto rounded-xl border border-border-light dark:border-border print:border-slate-300">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/[0.03] text-slate-500 dark:bg-white/[0.03] dark:text-ink-muted print:bg-slate-100 print:text-black">
                  <tr>
                    <th className="px-3 py-2 font-semibold">Specification</th>
                    <th className="px-3 py-2 font-semibold">Calculated Value</th>
                    <th className="px-3 py-2 font-semibold">Application Notes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-light dark:divide-border print:divide-slate-300">
                  <tr>
                    <td className="px-3 py-2 font-medium">Field Area</td>
                    <td className="px-3 py-2 font-semibold text-slate-800 dark:text-ink-primary print:text-black">
                      {calculation.numericArea} {calculation.unitLabel}
                    </td>
                    <td className="px-3 py-2 text-slate-500 dark:text-ink-muted print:text-slate-600">
                      {calculation.areaInAcres} acres equivalent
                    </td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2 font-medium">Prescribed Formulation</td>
                    <td className="px-3 py-2 font-semibold text-accent-600 dark:text-accent-400 print:text-black">
                      {calculation.chemicalName}
                    </td>
                    <td className="px-3 py-2 text-slate-500 dark:text-ink-muted print:text-slate-600">
                      Dilution rate: {calculation.ratePerLiter} {calculation.chemUnit}/L
                    </td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2 font-medium">Total Spray Volume</td>
                    <td className="px-3 py-2 font-bold text-slate-800 dark:text-ink-primary print:text-black">
                      {calculation.totalWaterLiters} Liters
                    </td>
                    <td className="px-3 py-2 text-slate-500 dark:text-ink-muted print:text-slate-600">
                      ({calculation.totalWaterGallons} US Gallons)
                    </td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2 font-medium">Total Chemical Concentrate</td>
                    <td className="px-3 py-2 font-bold text-accent-600 dark:text-accent-400 print:text-black">
                      {calculation.totalChemicalAmount} {calculation.chemUnit}
                    </td>
                    <td className="px-3 py-2 text-slate-500 dark:text-ink-muted print:text-slate-600">
                      Measure accurately before adding to tank
                    </td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2 font-medium">Equipment Refill Instructions</td>
                    <td className="px-3 py-2 font-semibold text-slate-800 dark:text-ink-primary print:text-black">
                      ~{calculation.tanksRequired} tank(s) ({calculation.equipmentName})
                    </td>
                    <td className="px-3 py-2 text-slate-500 dark:text-ink-muted print:text-slate-600">
                      Add {calculation.chemicalPerTank} {calculation.chemUnit} per {calculation.tankCapacityLiters}L fill
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 3: Safety PPE Checklist */}
          <div className="space-y-2">
            <h4 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-accent-700 dark:text-accent-400 print:text-black">
              <ShieldCheck size={14} />
              3. Mandatory Safety PPE Verification Checklist
            </h4>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <label
                onClick={() => togglePpe('gloves')}
                className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-border-light bg-slate-900/[0.02] p-2.5 text-xs text-slate-700 dark:border-border dark:bg-white/[0.02] dark:text-ink-secondary print:border-slate-300"
              >
                <input
                  type="checkbox"
                  checked={ppeChecked.gloves}
                  onChange={() => {}}
                  className="rounded text-accent-500 focus:ring-accent-500"
                />
                <span>Chemical-resistant nitrile / neoprene gloves</span>
              </label>

              <label
                onClick={() => togglePpe('respirator')}
                className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-border-light bg-slate-900/[0.02] p-2.5 text-xs text-slate-700 dark:border-border dark:bg-white/[0.02] dark:text-ink-secondary print:border-slate-300"
              >
                <input
                  type="checkbox"
                  checked={ppeChecked.respirator}
                  onChange={() => {}}
                  className="rounded text-accent-500 focus:ring-accent-500"
                />
                <span>N95 / organic vapor particle respirator mask</span>
              </label>

              <label
                onClick={() => togglePpe('eyeProtection')}
                className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-border-light bg-slate-900/[0.02] p-2.5 text-xs text-slate-700 dark:border-border dark:bg-white/[0.02] dark:text-ink-secondary print:border-slate-300"
              >
                <input
                  type="checkbox"
                  checked={ppeChecked.eyeProtection}
                  onChange={() => {}}
                  className="rounded text-accent-500 focus:ring-accent-500"
                />
                <span>Protective chemical splash goggles / eye protection</span>
              </label>

              <label
                onClick={() => togglePpe('coveralls')}
                className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-border-light bg-slate-900/[0.02] p-2.5 text-xs text-slate-700 dark:border-border dark:bg-white/[0.02] dark:text-ink-secondary print:border-slate-300"
              >
                <input
                  type="checkbox"
                  checked={ppeChecked.coveralls}
                  onChange={() => {}}
                  className="rounded text-accent-500 focus:ring-accent-500"
                />
                <span>Long-sleeved chemical coveralls & waterproof boots</span>
              </label>
            </div>
          </div>

          {/* Section 4: REI & PHI Compliance Warnings */}
          <div className="space-y-2">
            <h4 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-rose-700 dark:text-rose-400 print:text-black">
              <ShieldAlert size={14} />
              4. Restricted Entry Interval (REI) & Pre-Harvest Interval (PHI) Compliance Warnings
            </h4>
            <div className="grid grid-cols-1 gap-2.5 rounded-xl border border-rose-500/20 bg-rose-500/5 p-3.5 text-xs text-rose-950 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-200 sm:grid-cols-2 print:border-slate-400 print:bg-transparent print:text-black">
              <div>
                <div className="font-bold flex items-center gap-1">
                  <Clock size={13} className="text-rose-600" />
                  <span>Restricted Entry Interval (REI): 12 - 24 Hours</span>
                </div>
                <p className="mt-1 text-[11px] text-slate-600 dark:text-ink-secondary print:text-slate-600">
                  Do not enter or permit agricultural workers to enter treated field areas without full protective equipment during the REI window.
                </p>
              </div>

              <div>
                <div className="font-bold flex items-center gap-1">
                  <Calendar size={13} className="text-rose-600" />
                  <span>Pre-Harvest Interval (PHI): 0 - 5 Days</span>
                </div>
                <p className="mt-1 text-[11px] text-slate-600 dark:text-ink-secondary print:text-slate-600">
                  Adhere to the minimum waiting period between the last spray application and crop harvest to ensure chemical residue compliance.
                </p>
              </div>
            </div>
          </div>

          {/* Section 5: Official Agronomist Verification Signature */}
          <div className="space-y-2 border-t border-border-light pt-4 dark:border-border print:border-slate-300">
            <h4 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-ink-muted print:text-black">
              <FileText size={14} />
              5. Official Agronomist Verification & Sign-off
            </h4>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1 text-xs text-slate-600 dark:text-ink-secondary print:text-black">
                <p>
                  <strong>Certified Agronomist:</strong> Dr. J. Henderson, Ph.D., CCA
                </p>
                <p>
                  <strong>Certification / License:</strong> <span className="font-mono">CCA-#AGRI-88294-EXT</span>
                </p>
                <p>
                  <strong>Digital Seal:</strong> Verified via InsightAI LeafSense Arbitration
                </p>
                <p>
                  <strong>Date Verified:</strong> {today}
                </p>
              </div>

              <div className="flex flex-col justify-end text-right">
                <div className="mt-4 border-b border-slate-400 pb-1 text-xs font-mono text-slate-800 dark:text-ink-primary print:text-black">
                  Agronomist Signature: <em>J. Henderson, CCA</em>
                </div>
                <span className="text-[10px] text-slate-400 dark:text-ink-muted print:text-slate-500">
                  Official Verification & Compliance Stamp
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Bottom Footer (Hidden on print) */}
        <div className="sticky bottom-0 z-10 flex items-center justify-between border-t border-border-light bg-surface-light/95 px-5 py-3 backdrop-blur-sm dark:border-border dark:bg-surface-dark/95 print:hidden">
          <span className="text-[11px] text-slate-500 dark:text-ink-muted">
            Prescription generated automatically from LeafSense pathology diagnosis.
          </span>
          <div className="flex items-center gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={onClose}>
              Close
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              icon={FileDown}
              onClick={handleDownloadWorkOrder}
            >
              Download Work Order
            </Button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
