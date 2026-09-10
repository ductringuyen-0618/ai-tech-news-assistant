import { test, expect, type Route } from '@playwright/test';

/**
 * Learning tab (proposal 003) — mocks `GET /api/learning/` so the test is
 * deterministic and doesn't depend on the ingestion pipeline having run.
 * Mirrors the mocking convention used by saved-research.spec.ts.
 */

const MOCK_ITEM = {
  id: 1,
  title: 'New MCP server for agent workflows',
  source: 'Hacker News',
  url: 'https://example.com/mcp-server',
  published_at: new Date().toISOString(),
  image_url: null,
  categories: ['Agent Skills'],
  summary: 'A new Model Context Protocol server for streamlining agent setups.',
};

async function mockLearningApi(
  page: import('@playwright/test').Page,
  items: unknown[]
) {
  await page.route('**/api/learning/**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: items,
        pagination: {
          page: 1,
          page_size: 20,
          total_items: items.length,
          total_pages: items.length > 0 ? 1 : 0,
          has_next: false,
          has_previous: false,
          next_cursor: null,
        },
      }),
    });
  });
}

test.describe('Learning tab', () => {
  test('renders items from a mocked /api/learning/ response', async ({
    page,
  }) => {
    await mockLearningApi(page, [MOCK_ITEM]);

    await page.goto('/');
    await page.getByRole('tab', { name: /Learning/i }).click();

    await expect(page.getByRole('heading', { name: 'Learning' })).toBeVisible();

    const card = page.getByTestId('learning-card').first();
    await expect(card).toBeVisible();
    await expect(card.getByText(MOCK_ITEM.title)).toBeVisible();
    await expect(
      page.getByTestId('learning-card-summary').first()
    ).toContainText('Model Context Protocol');
    await expect(card.getByText('Hacker News')).toBeVisible();
    await expect(card.getByText('Agent Skills')).toBeVisible();

    const readMore = page.getByTestId('learning-card-read-more').first();
    await expect(readMore).toHaveAttribute('href', MOCK_ITEM.url);
    await expect(readMore).toHaveAttribute('target', '_blank');
  });

  test('shows an empty state when there are no items yet', async ({ page }) => {
    await mockLearningApi(page, []);

    await page.goto('/');
    await page.getByRole('tab', { name: /Learning/i }).click();

    await expect(page.getByTestId('learning-empty')).toBeVisible();
    await expect(page.getByTestId('learning-card')).toHaveCount(0);
  });

  test('shows an error state when the API call fails', async ({ page }) => {
    await page.route('**/api/learning/**', async (route: Route) => {
      await route.fulfill({ status: 500, body: 'boom' });
    });

    await page.goto('/');
    await page.getByRole('tab', { name: /Learning/i }).click();

    await expect(page.getByTestId('learning-error')).toBeVisible();
  });
});
