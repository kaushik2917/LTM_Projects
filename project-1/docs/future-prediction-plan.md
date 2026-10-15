# Future prediction implementation plan

Repository inspection completed before editing application code. Preserve Next.js/React, FastAPI, SQLite audit JSON, existing routes/styles, models and safe simulation.

1. Record dataset schemas/counts/hashes and prediction readiness. Dataset 10 contains alternative responses, dataset 11 synthetic rule labels, dataset 12 unordered quality rows, dataset 13 synthetic benchmark descriptors. ATT&CK is vocabulary; OpTC is not imported.
2. Add an explicit event-sequence contract, strict timestamp filtering, prefix-only features, and next observed labelled-event sample construction. Reject ambiguous ordering, malformed data and leakage. Keep synthetic pipeline tests explicitly synthetic.
3. Provide reproducible grouped training/validation/holdout, independent baseline comparison, ranking/classification/calibration diagnostics, errors and artifact provenance. Do not activate a genuine model without qualified data and passed checks.
4. Extend existing prediction route, audit/report JSON, graph cutoff and prevention context. Retain the original synthetic next-stage model in a separately named result.
5. Keep current UI structure; display genuine prediction readiness separately from synthetic demonstrations, timestamps, evidence inputs, model details and evaluation status.
6. Test cutoff isolation, future mutations, group/duplicate/label checks, inference, API persistence, every page and simulation. Document measured results and unavailable claims.

No new dataset download or invented observed labels. No real host response actions.
