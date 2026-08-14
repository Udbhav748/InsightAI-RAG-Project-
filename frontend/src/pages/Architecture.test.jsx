import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import Architecture from './Architecture'

describe('Architecture Page - System Architecture & Production AI Design Review', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders header, title, and initial 10 Questions tab by default', () => {
    render(<Architecture />)

    expect(screen.getByText('System Architecture & Production AI Design Review')).toBeInTheDocument()
    expect(screen.getByText('10 Production AI Questions')).toBeInTheDocument()
    expect(screen.getByText('LeafSense Vision & Confusion Matrix')).toBeInTheDocument()
    expect(screen.getByText('Multimodal RAG & StateGraph')).toBeInTheDocument()
    expect(screen.getByText('Security, Cost & Scaling')).toBeInTheDocument()

    // Question 1 is expanded by default
    expect(screen.getByText('01')).toBeInTheDocument()
    expect(screen.getByText('Why does this need an LLM?')).toBeInTheDocument()
    expect(screen.getByText(/Multi-Source Knowledge Synthesis/)).toBeInTheDocument()
  })

  it('expands and collapses questions when clicked', () => {
    render(<Architecture />)

    const q2Header = screen.getByText('What decisions are delegated to the LLM?')
    fireEvent.click(q2Header)

    expect(screen.getByText('Delegated to LLM')).toBeInTheDocument()
    expect(screen.getByText('Strictly Deterministic (Code / DB)')).toBeInTheDocument()
  })

  it('switches to LeafSense Vision & Confusion Matrix tab and changes crop views', () => {
    render(<Architecture />)

    const visionTabBtn = screen.getByText('LeafSense Vision & Confusion Matrix')
    fireEvent.click(visionTabBtn)

    expect(screen.getByText('38 Classes')).toBeInTheDocument()
    expect(screen.getByText('98.24%')).toBeInTheDocument()
    expect(screen.getByText('Interactive Confusion Matrix & Per-Class Precision')).toBeInTheDocument()

    // Switch crop to Apple
    const appleBtn = screen.getByRole('button', { name: 'Apple' })
    fireEvent.click(appleBtn)

    expect(screen.getByText(/Apple Model Accuracy:/)).toBeInTheDocument()
    expect(screen.getAllByText('Apple Scab').length).toBeGreaterThanOrEqual(1)
  })

  it('switches to Multimodal RAG & StateGraph tab and displays RRF formulas', () => {
    render(<Architecture />)

    const ragTabBtn = screen.getByText('Multimodal RAG & StateGraph')
    fireEvent.click(ragTabBtn)

    expect(screen.getByText('Multi-Agent StateGraph & Corrective RAG Runtime')).toBeInTheDocument()
    expect(screen.getByText('01. Vision Inference')).toBeInTheDocument()
    expect(screen.getByText('03. Hybrid Search (RRF)')).toBeInTheDocument()
    expect(screen.getByText('Reciprocal Rank Fusion (RRF) Formulation')).toBeInTheDocument()
  })

  it('switches to Security, Cost & Scaling tab', () => {
    render(<Architecture />)

    const secTabBtn = screen.getByText('Security, Cost & Scaling')
    fireEvent.click(secTabBtn)

    expect(screen.getByText('Multi-Tenant Isolation Architecture')).toBeInTheDocument()
    expect(screen.getByText('10 to 1,000,000 Scaling Roadmap')).toBeInTheDocument()
  })
})
