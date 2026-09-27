// Power Query (M) - dim_series
// Loads the series dimension. Demonstrates: source parameterisation, promoting
// headers, explicit type setting, column standardisation, and a derived field.
//
// SourceFolder is a parameter (defined in Power BI) pointing at data/processed.
let
    Source = Csv.Document(
        File.Contents(SourceFolder & "\dim_series.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),

    // Data-type normalisation
    Typed = Table.TransformColumnTypes(Promoted, {
        {"series_key", Int64.Type},
        {"series_id", type text},
        {"series_name", type text},
        {"category", type text},
        {"subcategory", type text},
        {"unit", type text},
        {"frequency", type text},
        {"measure_type", type text},
        {"source_key", type text}
    }),

    // Column standardisation: trim/clean text keys so joins never break on stray
    // whitespace introduced upstream.
    Cleaned = Table.TransformColumns(Typed, {
        {"series_id", each Text.Trim(_), type text},
        {"category", each Text.Proper(Text.Trim(_)), type text}
    }),

    // Derived field: a friendly unit label for report tooltips.
    WithUnitLabel = Table.AddColumn(Cleaned, "unit_label", each
        if [unit] = "percent" then "%"
        else if [unit] = "millions_cad" then "CAD millions"
        else if [unit] = "ratio" then "ratio"
        else [unit], type text)
in
    WithUnitLabel
