// Power Query (M) - dim_date
// Loads the daily calendar dimension. Demonstrates: explicit typing and
// date-part derivation done in the transformation layer (kept out of DAX).
let
    Source = Csv.Document(
        File.Contents(SourceFolder & "\dim_date.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"date_key", Int64.Type},
        {"date", type date},
        {"year", Int64.Type},
        {"quarter", Int64.Type},
        {"month", Int64.Type},
        {"month_name", type text},
        {"year_month", type text},
        {"year_quarter", type text},
        {"day_of_month", Int64.Type},
        {"is_month_end", type logical},
        {"is_quarter_end", type logical}
    }),
    // Derived sort key so month names sort chronologically in visuals.
    WithMonthSort = Table.AddColumn(Typed, "year_month_sort",
        each [year] * 100 + [month], Int64.Type)
in
    WithMonthSort
