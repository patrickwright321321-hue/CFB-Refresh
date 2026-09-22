# CFB Refresh

Safe staging repository for the College Football Prediction Model weekly data refresh.

## Production safety
- Do not write directly to ATS 4.1 Production from test code.
- Do not modify the `Live Odds` sheet.
- Do not change the frozen PR2.1 / ATS betting calculations.
- Highlightly is initially test/recovery-only until validated against trusted SportsDataverse/ESPN data.

## Required GitHub Actions secret
Create this repository secret:

`HIGHLIGHTLY_API_KEY`

Path in GitHub:
Settings → Secrets and variables → Actions → New repository secret

Never commit the API key to this repository.

## Test workflow
The Highlightly compatibility test is manual-only for now. It verifies that the secret is present without printing it and provides the safe place to add authenticated data-comparison code.
