// Power Query (M) - monitoring_alerts
// Loads the latest-period monitoring alerts. Demonstrates: filtering to active
// alerts, boolean typing, and a derived severity-order column for sorting.
let
    Source = Csv.Document(
        File.Contents(SourceFolder & "\monitoring_alerts.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"series_id", type text},
        {"series_name", type text},
        {"category", type text},
        {"observation_date", type date},
        {"value", type number},
        {"zscore", type number},
        {"pct_change", type number},
        {"severity", type text},
        {"reason", type text},
        {"is_alert", type logical}
    }),
    // Keep only rows the monitor actually flagged for the dashboard alert list.
    ActiveAlerts = Table.SelectRows(Typed, each [is_alert] = true),
    // Derived sort order so HIGH sorts above MEDIUM in a table visual.
    WithOrder = Table.AddColumn(ActiveAlerts, "severity_order", each
        if [severity] = "HIGH" then 1 else if [severity] = "MEDIUM" then 2 else 3,
        Int64.Type)
in
    WithOrder
