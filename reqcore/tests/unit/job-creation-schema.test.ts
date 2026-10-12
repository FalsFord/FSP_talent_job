import { describe, expect, it } from 'vitest'
import { createJobSchema, createJobWizardSchema } from '../../server/utils/schemas/job'
import { createQuestionSchema, questionStateSchema } from '../../server/utils/schemas/jobQuestion'

describe('job creation validation', () => {
  it('rejects whitespace-only titles and trims valid text fields', () => {
    expect(createJobSchema.safeParse({ title: '   ' }).success).toBe(false)

    const result = createJobSchema.parse({
      title: '  Senior QA Engineer  ',
      description: '  Build reliable systems.  ',
      location: '  Remote  ',
    })

    expect(result.title).toBe('Senior QA Engineer')
    expect(result.description).toBe('Build reliable systems.')
    expect(result.location).toBe('Remote')
  })

  it('rejects duplicate select options after trimming and case folding', () => {
    const result = createQuestionSchema.safeParse({
      label: 'Preferred framework?',
      type: 'single_select',
      options: ['Playwright', ' playwright '],
    })

    expect(result.success).toBe(false)
  })

  it('rejects invalid select question state after applying a partial update', () => {
    expect(questionStateSchema.safeParse({
      type: 'single_select',
      options: null,
    }).success).toBe(false)

    expect(questionStateSchema.safeParse({
      type: 'multi_select',
      options: ['Playwright', ' playwright '],
    }).success).toBe(false)

    expect(questionStateSchema.safeParse({
      type: 'single_select',
      options: ['Playwright'],
    }).success).toBe(true)
  })

  it('rejects impossible automatic-scoring and duplicate-criterion payloads', () => {
    expect(createJobWizardSchema.safeParse({
      title: 'QA Engineer',
      autoScoreOnApply: true,
      criteria: [],
    }).success).toBe(false)

    const criterion = {
      key: 'quality',
      name: 'Quality',
      category: 'technical' as const,
      maxScore: 10,
      weight: 50,
      displayOrder: 0,
    }
    expect(createJobWizardSchema.safeParse({
      title: 'QA Engineer',
      criteria: [criterion, { ...criterion, name: 'Quality duplicate' }],
    }).success).toBe(false)
  })

  it('caps nested records before they reach the transaction', () => {
    const questions = Array.from({ length: 51 }, (_, index) => ({
      label: `Question ${index}`,
      type: 'short_text' as const,
      required: false,
      displayOrder: index,
    }))

    expect(createJobWizardSchema.safeParse({
      title: 'QA Engineer',
      questions,
    }).success).toBe(false)
  })
})
