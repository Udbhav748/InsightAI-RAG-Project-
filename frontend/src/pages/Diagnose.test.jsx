import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import Diagnose from './Diagnose'
import * as diagnoseService from '../services/diagnoseService'
import * as documentService from '../services/documentService'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}))

const mockShowToast = vi.fn()
vi.mock('../hooks/useToast', () => ({
  default: () => ({ showToast: mockShowToast }),
}))

vi.mock('../services/documentService', () => ({
  getDocumentName: vi.fn((id) => (id === 'doc-agri-1' ? 'Tomato_Pathology_Guide.pdf' : null)),
}))

vi.mock('../services/diagnoseService', () => ({
  diagnoseLeaf: vi.fn(),
  diagnoseImageStream: vi.fn(),
  checkLeafSenseHealth: vi.fn(),
}))

function selectTestFile(file) {
  const dropzone = screen.getByTestId('leaf-dropzone')
  fireEvent.drop(dropzone, {
    dataTransfer: {
      files: [file],
    },
  })
}

describe('Diagnose Page - Plant Leaf Disease Diagnostic & Treatment Hub', () => {
  const mockDiagnosisResult = {
    answer: 'The leaf exhibits symptoms of Early Blight caused by Alternaria solani [1]. Immediate preventative fungicide or bio-remedies are recommended.',
    sources: [
      {
        chunk_id: 'chunk-agri-1',
        document_id: 'doc-agri-1',
        number: 1,
        page_number: 12,
        excerpt: 'Alternaria solani produces characteristic target-board concentric ring spots on tomato leaves.',
      },
    ],
    processing_time: 1.28,
    session_id: 'session-agri-test-123',
    diagnosis: {
      raw_class: 'Tomato___Early_blight',
      crop: 'tomato',
      disease: 'early blight',
      confidence: 0.95,
      low_confidence: false,
    },
  }

  beforeEach(() => {
    vi.clearAllMocks()
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:http://localhost/mock-leaf-preview')
    globalThis.URL.revokeObjectURL = vi.fn()
    diagnoseService.checkLeafSenseHealth.mockResolvedValue({
      online: true,
      port: 8001,
      url: 'http://localhost:8001',
      status: 'ok',
    })
    diagnoseService.diagnoseLeaf.mockResolvedValue(mockDiagnosisResult)
    diagnoseService.diagnoseImageStream.mockImplementation(async (file, query, onEvent) => {
      onEvent?.({
        type: 'diagnosis',
        diagnosis: mockDiagnosisResult.diagnosis,
      })
      onEvent?.({
        type: 'answer_chunk',
        text: mockDiagnosisResult.answer,
      })
      onEvent?.({
        type: 'done',
        payload: mockDiagnosisResult,
      })
    })
  })

  it('renders header, service health indicator, and upload dropzone', async () => {
    render(<Diagnose />)

    expect(screen.getByText('Plant Leaf Disease Diagnostic & Treatment Hub')).toBeInTheDocument()
    expect(
      screen.getByText(/Upload or capture a leaf photo/i)
    ).toBeInTheDocument()

    // Service health indicator online
    await waitFor(() => {
      expect(screen.getByText(/LeafSense Vision Engine Active/i)).toBeInTheDocument()
      expect(screen.getByText('Port 8001')).toBeInTheDocument()
    })

    // Action buttons
    expect(screen.getByRole('button', { name: 'Upload leaf photo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Take leaf photo' })).toBeInTheDocument()
    expect(screen.getByText('Choose from Gallery / Files')).toBeInTheDocument()
  })

  it('handles image selection, shows preview, and handles image removal', async () => {
    render(<Diagnose />)

    const file = new File(['fake-leaf-bytes'], 'tomato_early_blight.jpg', { type: 'image/jpeg' })
    selectTestFile(file)

    // Preview should now appear
    await waitFor(() => {
      expect(screen.getByText('tomato_early_blight.jpg')).toBeInTheDocument()
      const previewImg = screen.getByAltText('Plant leaf preview')
      expect(previewImg).toBeInTheDocument()
      expect(previewImg).toHaveAttribute('src', 'blob:http://localhost/mock-leaf-preview')
    })

    // Context input should be present
    expect(screen.getByPlaceholderText(/Add any specific context, crop stage, or question/i)).toBeInTheDocument()

    // Remove photo
    const removeBtn = screen.getByRole('button', { name: 'Remove image' })
    fireEvent.click(removeBtn)

    // Should return to dropzone
    await waitFor(() => {
      expect(screen.queryByAltText('Plant leaf preview')).not.toBeInTheDocument()
      expect(screen.getByText('Choose from Gallery / Files')).toBeInTheDocument()
    })
  })

  it('submits leaf photo, displays analyzing state, and renders prediction hero card with memory bridge', async () => {
    render(<Diagnose />)

    const file = new File(['fake-leaf-bytes'], 'tomato_leaf.png', { type: 'image/png' })
    selectTestFile(file)

    await waitFor(() => {
      expect(screen.getByAltText('Plant leaf preview')).toBeInTheDocument()
    })

    // Add optional context
    const contextInput = screen.getByPlaceholderText(/Add any specific context/i)
    fireEvent.change(contextInput, { target: { value: 'Observed yellow halos on bottom leaves' } })

    // Click Diagnose button
    const diagnoseBtn = screen.getByRole('button', { name: /Diagnose Plant Leaf/i })
    fireEvent.click(diagnoseBtn)

    expect(diagnoseService.diagnoseImageStream).toHaveBeenCalledWith(
      file,
      expect.objectContaining({
        query: 'Observed yellow halos on bottom leaves',
        engine: 'hybrid',
      }),
      expect.any(Function),
      expect.any(Function)
    )

    // Wait for Hero Card to render
    await waitFor(() => {
      expect(screen.getByText('early blight')).toBeInTheDocument()
    })

    // Validate Prediction Hero Card details
    expect(screen.getByText('tomato')).toBeInTheDocument()
    expect(screen.getByTestId('severity-badge')).toHaveTextContent(/Severity:\s*(Severe|Moderate)/i)
    expect(screen.getByTestId('confidence-score-value')).toHaveTextContent('95%')
    expect(screen.getByText('Tomato___Early_blight')).toBeInTheDocument()

    // Action buttons
    const chatBtn = screen.getByTestId('continue-in-chat-button')
    expect(chatBtn).toBeInTheDocument()
    expect(screen.getByTestId('download-prescription-button')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Diagnose Another Leaf/i })).toBeInTheDocument()

    // Test navigating to chat with URL search parameters and state memory bridge
    fireEvent.click(chatBtn)
    expect(mockNavigate).toHaveBeenCalledWith(
      '/chat?crop=tomato&disease=early+blight&severity=Severe',
      expect.objectContaining({
        state: expect.objectContaining({
          sessionId: 'session-agri-test-123',
          crop: 'tomato',
          disease: 'early blight',
        }),
      })
    )
  })

  it('displays OOD Non-Leaf Gatekeeper warning banner when confidence is low or flagged uncertain', async () => {
    const oodResult = {
      ...mockDiagnosisResult,
      diagnosis: {
        raw_class: 'background_non_leaf',
        crop: 'non-leaf',
        disease: 'uncertain condition',
        confidence: 0.34,
        low_confidence: true,
        is_non_leaf: true,
      },
    }

    diagnoseService.diagnoseImageStream.mockImplementationOnce(async (file, query, onEvent) => {
      onEvent?.({
        type: 'diagnosis',
        diagnosis: oodResult.diagnosis,
      })
      onEvent?.({
        type: 'answer_chunk',
        text: oodResult.answer,
      })
      onEvent?.({
        type: 'done',
        payload: oodResult,
      })
    })

    render(<Diagnose />)

    const file = new File(['fake-random-object-bytes'], 'random_desk_photo.jpg', { type: 'image/jpeg' })
    selectTestFile(file)

    await waitFor(() => {
      expect(screen.getByAltText('Plant leaf preview')).toBeInTheDocument()
    })

    const diagnoseBtn = screen.getByRole('button', { name: /Diagnose Plant Leaf/i })
    fireEvent.click(diagnoseBtn)

    await waitFor(() => {
      expect(
        screen.getAllByText(/Low Visual Confidence \/ Non-Plant Detected/i).length
      ).toBeGreaterThan(0)
    })

    expect(
      screen.getAllByText(/Please ensure the photo is well-lit and clearly shows an infected crop leaf/i).length
    ).toBeGreaterThan(0)
  })

  it('progressively streams diagnosis: immediately displays hero card on diagnosis event, streams tokens, and finalizes on done', async () => {
    let emitEvent
    diagnoseService.diagnoseImageStream.mockImplementation(async (file, query, onEvent) => {
      emitEvent = onEvent
    })

    render(<Diagnose />)

    const file = new File(['fake-leaf-bytes'], 'tomato_early_blight.png', { type: 'image/png' })
    selectTestFile(file)

    await waitFor(() => {
      expect(screen.getByAltText('Plant leaf preview')).toBeInTheDocument()
    })

    const diagnoseBtn = screen.getByRole('button', { name: /Diagnose Plant Leaf/i })
    fireEvent.click(diagnoseBtn)

    // 1. Sub-second diagnosis event arrives immediately
    act(() => {
      emitEvent({
        type: 'diagnosis',
        diagnosis: {
          raw_class: 'Tomato___Early_blight',
          crop: 'tomato',
          disease: 'early blight',
          confidence: 0.95,
          low_confidence: false,
        },
      })
    })

    // Prediction Hero Card renders immediately
    await waitFor(() => {
      expect(screen.getByText('early blight')).toBeInTheDocument()
    })
    expect(screen.getByText('tomato')).toBeInTheDocument()
    expect(screen.getByTestId('severity-badge')).toHaveTextContent(/Severity:\s*(Severe|Moderate)/i)
    expect(screen.getByTestId('confidence-score-value')).toHaveTextContent('95%')
    expect(screen.getByText(/Streaming response\.\.\./i)).toBeInTheDocument()

    // 2. Stream tokens arrive in real-time
    act(() => {
      emitEvent({
        type: 'answer_chunk',
        text: 'Early Blight initial symptoms detected. ',
      })
    })

    await waitFor(() => {
      expect(screen.getByText(/Early Blight initial symptoms detected/i)).toBeInTheDocument()
    })

    act(() => {
      emitEvent({
        type: 'answer_chunk',
        text: 'Apply Copper Hydroxide spray immediately.',
      })
    })

    await waitFor(() => {
      expect(
        screen.getByText(/Early Blight initial symptoms detected\. Apply Copper Hydroxide spray immediately\./i)
      ).toBeInTheDocument()
    })

    // User can switch tabs while streaming
    const tabOrganic = screen.getByRole('tab', { name: /Organic Remedies/i })
    fireEvent.click(tabOrganic)
    await waitFor(() => {
      expect(screen.getByText(/Biological Fungicides & Antagonists/i)).toBeInTheDocument()
    })

    // Switch back to overview tab
    const tabOverview = screen.getByRole('tab', { name: /Overview & Symptoms/i })
    fireEvent.click(tabOverview)

    // 3. Done event arrives and finalizes
    act(() => {
      emitEvent({
        type: 'done',
        payload: {
          ...mockDiagnosisResult,
          answer: 'Early Blight initial symptoms detected. Apply Copper Hydroxide spray immediately.',
        },
      })
    })

    await waitFor(() => {
      expect(screen.queryByText(/Streaming response\.\.\./i)).not.toBeInTheDocument()
    })
  })

  it('filters active chemical ingredients dynamically based on regional regulatory jurisdiction (EFSA & OMRI)', async () => {
    diagnoseService.diagnoseLeaf.mockResolvedValueOnce(mockDiagnosisResult)

    render(<Diagnose />)

    const file = new File(['fake-bytes'], 'tomato_leaf.png', { type: 'image/png' })
    selectTestFile(file)

    await waitFor(() => {
      expect(screen.getByAltText('Plant leaf preview')).toBeInTheDocument()
    })

    const diagnoseBtn = screen.getByRole('button', { name: /Diagnose Plant Leaf/i })
    fireEvent.click(diagnoseBtn)

    await waitFor(() => {
      expect(screen.getByText('early blight')).toBeInTheDocument()
    })

    // Navigate to Tab 3: Chemical Control & Dosages
    const tabChemical = screen.getByRole('tab', { name: /Chemical Control & Dosages/i })
    fireEvent.click(tabChemical)

    await waitFor(() => {
      expect(screen.getByTestId('regulatory-jurisdiction-select')).toBeInTheDocument()
    })

    const jurisdictionSelect = screen.getByTestId('regulatory-jurisdiction-select')

    // 1. Select European Union (EFSA)
    fireEvent.change(jurisdictionSelect, { target: { value: 'EFSA' } })

    await waitFor(() => {
      expect(screen.getByText(/Non-Renewed in EU \/ Restricted/i)).toBeInTheDocument()
      expect(screen.getByText(/Phase-out in EU/i)).toBeInTheDocument()
    })

    // Approved synthetic like Azoxystrobin is compliant under EFSA
    expect(screen.getAllByText(/EFSA Compliant/i).length).toBeGreaterThan(0)

    // 2. Select Global Organic (OMRI Only)
    fireEvent.change(jurisdictionSelect, { target: { value: 'OMRI' } })

    await waitFor(() => {
      expect(screen.getAllByText(/Prohibited \(OMRI Organic\)/i).length).toBeGreaterThan(0)
      expect(screen.getByText(/Global Organic \(OMRI Only\) Active/i)).toBeInTheDocument()
    })
  })

  it('opens and formats downloadable/printable spray prescription work order with PPE, REI/PHI, and Agronomist verification', async () => {
    diagnoseService.diagnoseLeaf.mockResolvedValueOnce(mockDiagnosisResult)

    render(<Diagnose />)

    const file = new File(['fake-bytes'], 'tomato_leaf.png', { type: 'image/png' })
    selectTestFile(file)

    await waitFor(() => {
      expect(screen.getByAltText('Plant leaf preview')).toBeInTheDocument()
    })

    const diagnoseBtn = screen.getByRole('button', { name: /Diagnose Plant Leaf/i })
    fireEvent.click(diagnoseBtn)

    await waitFor(() => {
      expect(screen.getByTestId('download-prescription-button')).toBeInTheDocument()
    })

    // Click Download Spray Prescription Work Order button
    const prescriptionBtn = screen.getByTestId('download-prescription-button')
    fireEvent.click(prescriptionBtn)

    // Modal should be open
    await waitFor(() => {
      expect(screen.getByTestId('prescription-work-order-document')).toBeInTheDocument()
    })

    // Verify key prescription sections:
    // 1. Patient / Crop
    expect(screen.getAllByText(/tomato/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/early blight/i).length).toBeGreaterThan(0)

    // 2. Dosage Calculations
    expect(screen.getByText('Total Spray Volume')).toBeInTheDocument()
    expect(screen.getByText('Total Chemical Concentrate')).toBeInTheDocument()

    // 3. Safety PPE Checklist
    expect(screen.getByText(/Chemical-resistant nitrile \/ neoprene gloves/i)).toBeInTheDocument()
    expect(screen.getByText(/N95 \/ organic vapor particle respirator mask/i)).toBeInTheDocument()
    expect(screen.getByText(/Protective chemical splash goggles/i)).toBeInTheDocument()

    // 4. REI & PHI Compliance Warnings
    expect(screen.getByText(/Restricted Entry Interval \(REI\): 12 - 24 Hours/i)).toBeInTheDocument()
    expect(screen.getByText(/Pre-Harvest Interval \(PHI\): 0 - 5 Days/i)).toBeInTheDocument()

    // 5. Official Agronomist Verification Signature Section
    expect(screen.getByText(/Certified Agronomist:/i)).toBeInTheDocument()
    expect(screen.getByText(/Dr\. J\. Henderson, Ph\.D\., CCA/i)).toBeInTheDocument()
    expect(screen.getByText(/Agronomist Signature:/i)).toBeInTheDocument()

    // Test Download action
    const downloadBtn = screen.getByRole('button', { name: /Download \(\.txt\)/i })
    expect(downloadBtn).toBeInTheDocument()
    fireEvent.click(downloadBtn)

    expect(globalThis.URL.createObjectURL).toHaveBeenCalled()

    // Test Close Modal
    const closeBtn = screen.getByLabelText(/Close prescription modal/i)
    fireEvent.click(closeBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('prescription-work-order-document')).not.toBeInTheDocument()
    })
  })

  it('switches between all 5 treatment tabs and renders structured agronomic content', async () => {
    diagnoseService.diagnoseLeaf.mockResolvedValueOnce(mockDiagnosisResult)

    render(<Diagnose />)

    const file = new File(['fake-bytes'], 'tomato_leaf.png', { type: 'image/png' })
    selectTestFile(file)

    await waitFor(() => {
      expect(screen.getByAltText('Plant leaf preview')).toBeInTheDocument()
    })

    const diagnoseBtn = screen.getByRole('button', { name: /Diagnose Plant Leaf/i })
    fireEvent.click(diagnoseBtn)

    await waitFor(() => {
      expect(screen.getByText('early blight')).toBeInTheDocument()
    })

    // Verify all 5 tab buttons exist
    const tabOverview = screen.getByRole('tab', { name: /Overview & Symptoms/i })
    const tabOrganic = screen.getByRole('tab', { name: /Organic Remedies/i })
    const tabChemical = screen.getByRole('tab', { name: /Chemical Control & Dosages/i })
    const tabPrevention = screen.getByRole('tab', { name: /Prevention Schedule/i })
    const tabSources = screen.getByRole('tab', { name: /Verified Sources & PDF Citations/i })

    expect(tabOverview).toBeInTheDocument()
    expect(tabOrganic).toBeInTheDocument()
    expect(tabChemical).toBeInTheDocument()
    expect(tabPrevention).toBeInTheDocument()
    expect(tabSources).toBeInTheDocument()

    // 1. Tab 1: Overview & Symptoms (active by default)
    expect(screen.getByText(/Primary Diagnostic Symptoms/i)).toBeInTheDocument()
    expect(screen.getByText(/concentric rings/i)).toBeInTheDocument()

    // 2. Tab 2: Organic Remedies
    fireEvent.click(tabOrganic)
    await waitFor(() => {
      expect(screen.getByText(/Biological Fungicides & Antagonists/i)).toBeInTheDocument()
    })
    expect(screen.getAllByText(/Bacillus subtilis/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Neem Oil/i).length).toBeGreaterThan(0)

    // 3. Tab 3: Chemical Control & Dosages
    fireEvent.click(tabChemical)
    await waitFor(() => {
      expect(screen.getByText(/Recommended Active Chemical Ingredients & Dosages/i)).toBeInTheDocument()
    })
    expect(screen.getAllByText(/Chlorothalonil 720 SC/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Mancozeb 75% WP/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/FRAC Resistance Management/i)).toBeInTheDocument()

    // 4. Tab 4: Prevention Schedule
    fireEvent.click(tabPrevention)
    await waitFor(() => {
      expect(screen.getByText(/4-Stage Seasonal Crop Protection Calendar/i)).toBeInTheDocument()
    })
    expect(screen.getByText('Pre-Planting')).toBeInTheDocument()
    expect(screen.getByText('Vegetative Growth')).toBeInTheDocument()
    expect(screen.getByText('Flowering & Fruiting')).toBeInTheDocument()
    expect(screen.getByText('Post-Harvest Cleanup')).toBeInTheDocument()

    // 5. Tab 5: Verified Sources & PDF Citations
    fireEvent.click(tabSources)
    await waitFor(() => {
      expect(screen.getByText(/RAG Retrieved Documents & Citations/i)).toBeInTheDocument()
    })
    expect(screen.getAllByText(/Tomato_Pathology_Guide\.pdf · page 12/i).length).toBeGreaterThan(0)
  })

  it('performs interactive spray dosage calculations when field size and units change', async () => {
    diagnoseService.diagnoseLeaf.mockResolvedValueOnce(mockDiagnosisResult)

    render(<Diagnose />)

    const file = new File(['fake-bytes'], 'tomato_leaf.png', { type: 'image/png' })
    selectTestFile(file)

    await waitFor(() => {
      expect(screen.getByAltText('Plant leaf preview')).toBeInTheDocument()
    })

    const diagnoseBtn = screen.getByRole('button', { name: /Diagnose Plant Leaf/i })
    fireEvent.click(diagnoseBtn)

    await waitFor(() => {
      expect(screen.getByText('Field Spray Dosage & Tank Mix Calculator')).toBeInTheDocument()
    })

    const fieldSizeInput = screen.getByTestId('field-size-input')
    const unitSelect = screen.getByTestId('area-unit-select')
    const chemicalSelect = screen.getByTestId('chemical-preset-select')

    expect(fieldSizeInput).toBeInTheDocument()
    expect(unitSelect).toBeInTheDocument()

    // Default: 1000 sq ft, Copper Hydroxide (2.5 g/L)
    const initialLiters = screen.getByTestId('water-volume-liters')
    expect(initialLiters).toHaveTextContent(/4\.35\s*L/i)
    expect(screen.getByTestId('chemical-amount-output')).toHaveTextContent(/10\.9\s*g/i)

    // Change Field Size to 5000 sq ft
    fireEvent.change(fieldSizeInput, { target: { value: '5000' } })
    expect(screen.getByTestId('water-volume-liters')).toHaveTextContent(/21\.73\s*L/i)
    expect(screen.getByTestId('chemical-amount-output')).toHaveTextContent(/54\.3\s*g/i)

    // Change Unit to Acres (2 acres)
    fireEvent.change(unitSelect, { target: { value: 'acres' } })
    fireEvent.change(fieldSizeInput, { target: { value: '2' } })

    expect(screen.getByTestId('water-volume-liters')).toHaveTextContent(/378\.54\s*L/i)
    expect(screen.getByTestId('chemical-amount-output')).toHaveTextContent(/946\.4\s*g/i)
    expect(screen.getByTestId('tank-refills-count')).toHaveTextContent(/~23\.7\s*tanks/i)

    // Change Chemical to Neem Oil (5 ml/L)
    fireEvent.change(chemicalSelect, { target: { value: 'neem' } })
    expect(screen.getByTestId('chemical-amount-output')).toHaveTextContent(/1892\.7\s*ml/i)
  })

  it('displays LeafSense offline error banner with actionable instructions when service is down', async () => {
    diagnoseService.checkLeafSenseHealth.mockResolvedValue({
      online: false,
      port: 8001,
      url: 'http://localhost:8001',
      message: 'Connection refused',
    })

    render(<Diagnose />)

    await waitFor(() => {
      expect(screen.getByTestId('leafsense-offline-banner')).toBeInTheDocument()
    })

    expect(screen.getByText('LeafSense Vision Service Offline (Port 8001)')).toBeInTheDocument()
    expect(screen.getByText(/uvicorn main:app --host localhost --port 8001/i)).toBeInTheDocument()
    expect(screen.getByText(/\.\/start-local\.ps1/i)).toBeInTheDocument()

    // Test Recheck button
    diagnoseService.checkLeafSenseHealth.mockResolvedValue({
      online: true,
      port: 8001,
      url: 'http://localhost:8001',
      status: 'ok',
    })

    const recheckBtn = screen.getByRole('button', { name: /Recheck Port 8001/i })
    fireEvent.click(recheckBtn)

    await waitFor(() => {
      expect(screen.getByText(/LeafSense Vision Engine Active/i)).toBeInTheDocument()
    })
  })
})
