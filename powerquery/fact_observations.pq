// Power Query (M) - fact_observations
// The main fact query. Demonstrates the transformations Power Query is best at:
//   * data-type normalisation
//   * filtering
//   * missing-value handling
//   * a derived, model-friendly field
//
// Note on layering: heavy row-level enrichment already happened in Python/SQL.
// Power Query here does the *last-mile* shaping the semantic model needs, which
// is exactly how it is used in practice alongside a governed data warehouse.
let
    Source = Csv.Document(
        File.Contents(SourceFolder & "\fact_observations.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),

    Typed = Table.TransformColumnTypes(Promoted, {
        {"series_key", Int64.Type},
        {"series_id", type text},
        {"date_key", Int64.Type},
        {"observation_date", type date},
        {"value", type number}
    }),

    // Preserve null source observations; they are missing, not estimated zeros.
    Tagged = Table.AddColumn(Typed, "is_missing", each [value] = null, type logical),

    // Filtering: drop any rows with an unparseable/blank observation date.
    Filtered = Table.SelectRows(Tagged, each [observation_date] <> null),

    // Keep the fact table at its declared grain; use the dim_series relationship
    // for category and measure-type filtering in the semantic model.
    WithDisplay = Table.AddColumn(Filtered, "value_display",
        each if [value] = null then null else Number.Round([value], 4), type number)
in
    WithDisplay
