import { expect, test, type Page } from "@playwright/test";

// The paths a reviewer takes through the demo, run against the real API and the seeded
// synthetic world. Selectors are roles and visible Korean text, the way a person finds things.

const opportunityCards = (page: Page) => page.locator('a[href^="/app/opportunities/"]');

async function signIn(page: Page, email: string, password: string) {
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
}

test("a visitor tries the demo, opens a tendered project and gets a brief", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /데모로 둘러보기/ }).click();

  await expect(page).toHaveURL(/\/app$/);
  // the feed opens on pre-tender demand
  await expect(page.getByRole("radio", { name: "공고 전" })).toHaveAttribute("aria-checked", "true");
  await expect(opportunityCards(page).first()).toBeVisible();
  await expect(opportunityCards(page).first()).toContainText("입찰 예상");

  await page.getByRole("radio", { name: "입찰 진행" }).click();
  await expect(opportunityCards(page).first()).toContainText("입찰공고");
  // the point of the product: among tendered projects, some were found before the tender
  const foundEarly = opportunityCards(page).filter({ hasText: /공고 .+ 전에 찾음/ }).first();
  await expect(foundEarly).toBeVisible();
  const tendered = foundEarly;

  await tendered.click();
  await expect(page).toHaveURL(/\/app\/opportunities\/\d+$/);
  await expect(page.getByText("영업 브리핑", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /브리핑 만들기|다시 만들기/ }).click();
  await expect(page.getByText("브리핑을 만들었어요. 크레딧 3개를 썼어요.")).toBeVisible();
  await expect(page.locator("article.prose-brief")).toBeVisible();
});

test("a signed-out visitor is sent to log in and comes back to the page they asked for", async ({ page }) => {
  await page.goto("/app/alerts");
  await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Falerts$/);

  await signIn(page, "care@example.com", "demo-pass-1234");

  await expect(page).toHaveURL(/\/app\/alerts$/);
});

test("the operator console shows the pipeline, and every chart can be read as a table", async ({ page }) => {
  await page.goto("/login");
  await signIn(page, "admin@example.com", "admin-pass-1234");

  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "운영 개요" })).toBeVisible();

  await page.getByRole("button", { name: "표로 보기" }).first().click();
  await expect(page.getByRole("table").first()).toBeVisible();
});
