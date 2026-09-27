// Power Query (M) - fact_observations
// The main fact query. Demonstrates the transformations Power Query is best at:
//   * data-type normalisation
//   * filtering
//   * missing-value handling
//   * a reference-data merge (join to dim_series to pull category/measure_type)
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

    // Missing-value handling: source suppressions arrive as null. Keep the row
    // (so the date axis stays continuous) but tag it for transparent reporting.
    Tagged = Table.AddColumn(Typed, "is_estimated_missing", each [value] = null, type logical),

    // Filtering: drop any rows with an unparseable/blank observation date.
    Filtered = Table.SelectRows(Tagged, each [observation_date] <> null),

    // Reference-data merge: bring measure_type + category from dim_series so the
    // fact can be filtered by analytical grouping without a model relationship
    // round-trip in some visuals.
    Merged = Table.NestedJoin(
        Filtered, {"series_key"}, dim_series, {"series_key"}, "series", JoinKind.LeftOuter
    ),
    Expanded = Table.ExpandTableColumn(
        Merged, "series", {"measure_type", "category"}, {"measure_type", "category"}
    ),

    // Derived field: signed value for rate vs balance shared visuals is not
    // needed, but a clean rounded display value is useful.
    WithDisplay = Table.AddColumn(Expanded, "value_display",
        each if [value] = null then null else Number.Round([value], 4), type number)
in
    WithDisplay
