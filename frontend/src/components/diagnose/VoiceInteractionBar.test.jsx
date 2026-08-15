import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import VoiceInteractionBar, {
  SpeechToTextButton,
  FieldProtocolAudioPlayer,
  buildEmergencyFieldProtocolText,
} from './VoiceInteractionBar'

describe('VoiceInteractionBar & Accessibility Suite', () => {
  const mockDiagnosis = {
    crop: 'tomato',
    disease: 'early blight',
    confidence: 0.94,
    raw_class: 'Tomato___Early_blight',
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('buildEmergencyFieldProtocolText', () => {
    it('generates a detailed emergency 24-48h script for diseased crop', () => {
      const script = buildEmergencyFieldProtocolText(mockDiagnosis)
      expect(script).toContain('Emergency 24 to 48-Hour Field Protocol for tomato affected by early blight')
      expect(script).toContain('Severity level: Severe')
      expect(script).toContain('94%')
      expect(script).toContain('Immediate Step 1: Cultural Sanitation')
      expect(script).toContain('Immediate Step 2: Biological Control')
      expect(script).toContain('Immediate Step 3: Chemical Treatment')
      expect(script).toContain('Safety Advisory: Always wear personal protective equipment')
    })

    it('generates healthy status reassurance script when disease is healthy', () => {
      const script = buildEmergencyFieldProtocolText({
        crop: 'apple',
        disease: 'healthy',
        confidence: 0.99,
      })
      expect(script).toContain('Field Health Report: Your apple foliage is diagnosed as healthy')
      expect(script).toContain('No chemical fungicide is required')
    })

    it('handles empty or missing diagnosis safely', () => {
      const script = buildEmergencyFieldProtocolText(null)
      expect(script).toBe('No active crop diagnosis available.')
    })
  })

  describe('SpeechToTextButton (STT)', () => {
    it('renders with accessible aria labels and toggles listening state on click', async () => {
      const handleTranscript = vi.fn()
      render(<SpeechToTextButton onTranscript={handleTranscript} />)

      const micButton = screen.getByTestId('speech-to-text-mic-button')
      expect(micButton).toBeInTheDocument()
      expect(micButton).toHaveAttribute('aria-label', 'Start hands-free voice dictation')

      fireEvent.click(micButton)

      await waitFor(() => {
        expect(screen.getByText(/Listening\.\.\. Speak clearly/i)).toBeInTheDocument()
      })
      expect(micButton).toHaveAttribute('aria-label', 'Stop voice recording')

      // Clicking again stops listening
      fireEvent.click(micButton)
      await waitFor(() => {
        expect(screen.queryByText(/Listening\.\.\. Speak clearly/i)).not.toBeInTheDocument()
      })
    })

    it('gracefully handles unsupported browsers', () => {
      const originalSR = window.SpeechRecognition
      const originalWSR = window.webkitSpeechRecognition
      delete window.SpeechRecognition
      delete window.webkitSpeechRecognition

      render(<SpeechToTextButton onTranscript={vi.fn()} />)

      const micButton = screen.getByTestId('speech-to-text-mic-button')
      expect(micButton).toBeDisabled()
      expect(micButton).toHaveAttribute('aria-label', 'Voice input not supported in this browser')

      // Restore
      window.SpeechRecognition = originalSR
      window.webkitSpeechRecognition = originalWSR
    })
  })

  describe('FieldProtocolAudioPlayer (TTS)', () => {
    it('renders soundwaves and triggers speech narration on play, pause, resume, and stop', async () => {
      render(<FieldProtocolAudioPlayer diagnosis={mockDiagnosis} />)

      expect(screen.getByTestId('field-protocol-audio-player')).toBeInTheDocument()
      expect(screen.getByTestId('audio-soundwave-bars')).toBeInTheDocument()

      const playBtn = screen.getByTestId('voice-play-protocol-button')
      expect(playBtn).toBeInTheDocument()
      expect(playBtn).toHaveTextContent('[ 🔊 Listen to 24h Field Protocol ]')

      // 1. Play
      fireEvent.click(playBtn)
      expect(window.speechSynthesis.speak).toHaveBeenCalledWith(
        expect.objectContaining({
          text: expect.stringContaining('Emergency 24 to 48-Hour Field Protocol'),
          rate: 0.95,
        })
      )

      // 2. Pause
      await waitFor(() => {
        expect(screen.getByTestId('voice-pause-protocol-button')).toBeInTheDocument()
      })
      const pauseBtn = screen.getByTestId('voice-pause-protocol-button')
      fireEvent.click(pauseBtn)
      expect(window.speechSynthesis.pause).toHaveBeenCalled()

      // 3. Resume
      const resumeBtn = screen.getByTestId('voice-play-protocol-button')
      expect(resumeBtn).toHaveTextContent('Resume')
      fireEvent.click(resumeBtn)
      expect(window.speechSynthesis.resume).toHaveBeenCalled()

      // 4. Stop
      const stopBtn = screen.getByTestId('voice-stop-protocol-button')
      fireEvent.click(stopBtn)
      expect(window.speechSynthesis.cancel).toHaveBeenCalled()
    })

    it('renders unsupported banner if speechSynthesis is unavailable', () => {
      const originalSpeechSynthesis = window.speechSynthesis
      delete window.speechSynthesis

      render(<FieldProtocolAudioPlayer diagnosis={mockDiagnosis} />)

      expect(screen.getByText('Audio narration unsupported in this browser')).toBeInTheDocument()

      // Restore
      window.speechSynthesis = originalSpeechSynthesis
    })
  })

  describe('Composite VoiceInteractionBar', () => {
    it('renders both audio player and dictation section when diagnosis and callback are provided', () => {
      const handleTranscript = vi.fn()
      render(
        <VoiceInteractionBar
          diagnosis={mockDiagnosis}
          onTranscript={handleTranscript}
        />
      )

      expect(screen.getByTestId('voice-interaction-bar')).toBeInTheDocument()
      expect(screen.getByTestId('field-protocol-audio-player')).toBeInTheDocument()
      expect(screen.getByText(/Hands-free Field Voice Dictation/i)).toBeInTheDocument()
      expect(screen.getByTestId('speech-to-text-mic-button')).toBeInTheDocument()
    })
  })
})
