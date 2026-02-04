# Vendor panel validation

- Status: **MISSING INPUTS**

## Inputs
- data/samples/growthepie/vendor_daily_rollup_panel_sample.csv (exists=False)

## Failures
- [inputs] missing_input_csv

## Next steps
- Generate the committed sample via W1 growthepie ETL (T030), then rerun: python src/validation/validate_vendor_panel.py --sample
