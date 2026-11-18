import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ReviewPage } from '../ReviewPage'
import { useReviewStatus } from '../../hooks/useReviewStatus'
import { apiClient } from '../../services/api'
import { Review } from '../../types'

// ReviewPage pulls review data from two places: useReviewStatus (polling)
// and apiClient.getReview (the full review, fetched once status is
// 'complete'). Mock both so we can drive status/error_message directly.
vi.mock('../../hooks/useReviewStatus')
vi.mock('../../services/api', () => ({
  apiClient: { getReview: vi.fn() }
}))

const baseReview: Review = {
  id: 'review-1',
  profile_id: 'profile-1',
  status: 'complete',
  overall_score: 0.81,
  sections: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
}

function renderReviewPage() {
  return render(
    <MemoryRouter initialEntries={['/reviews/review-1']}>
      <ReviewPage />
    </MemoryRouter>
  )
}

describe('ReviewPage tool-failure banner (issue #16)', () => {
  beforeEach(() => {
    vi.mocked(useReviewStatus).mockReturnValue({
      review: baseReview,
      isPolling: false,
      error: null
    })
  })

  it('shows a partial-failure banner when a complete review has an error_message', async () => {
    vi.mocked(apiClient.getReview).mockResolvedValue({
      ...baseReview,
      error_message: "Some analysis steps couldn't complete and were skipped: skill_extractor."
    })

    renderReviewPage()

    expect(
      await screen.findByText(/couldn't complete and were skipped: skill_extractor/i)
    ).toBeInTheDocument()
  })

  it('shows no banner when a complete review has no error_message', async () => {
    vi.mocked(apiClient.getReview).mockResolvedValue({ ...baseReview, error_message: undefined })

    renderReviewPage()

    await waitFor(() => expect(apiClient.getReview).toHaveBeenCalled())
    expect(screen.queryByText(/couldn't complete and were skipped/i)).not.toBeInTheDocument()
  })
})
