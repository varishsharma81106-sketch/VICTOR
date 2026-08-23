# GitHub Actions Workflows

## Grok AI Code Review

Automated code review using xAI's Grok on every pull request.

### Setup

1. **Get an xAI API key:**
   - Go to https://console.x.ai/
   - Create an account
   - Generate an API key

2. **Add the secret to GitHub:**
   - Go to your repo → Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `XAI_API_KEY`
   - Value: Your xAI API key

3. **Push to GitHub:**
   ```bash
   git add .github/
   git commit -m "ci: add Grok AI code review workflow"
   git push
   ```

### What It Does

On every pull request, Grok will:
1. Review all changed files
2. Check for logic errors in reasoning.py
3. Verify masking enforcement
4. Look for thread safety issues
5. Identify test coverage gaps
6. Post a review comment on the PR

### Customization

Edit `.github/workflows/grok-review.yml` to change the review prompt.

Current prompt focuses on Victor-specific concerns:
- NLI cross-encoder logic
- Masking enforcement
- Thread safety
- Token counting
- Test coverage

### Cost

xAI API costs apply. Check https://console.x.ai/ for pricing.

---

*Created: 2026-08-12*
