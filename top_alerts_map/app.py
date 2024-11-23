import pandas as pd
import altair as alt
import json
from pathlib import Path
from shiny import App, reactive, render, ui
from shinywidgets import render_altair, output_widget

# Define the path to the CSV and GeoJSON files and load the data
app_dir = Path(__file__).parent
df = pd.read_csv(app_dir / "top_alerts_map.csv")
geojson_file = app_dir / "chicago-boundaries.geojson"

# Load the GeoJSON file
with open(geojson_file) as f:
    chicago_geojson = json.load(f)

# Prepare Altair GeoJSON data
geo_data = alt.Data(values=chicago_geojson["features"])

# Prepare unique type-subtype combinations for the dropdown
df["type_subtype"] = df["updated_type"] + " - " + df["updated_subtype"]
unique_combinations = sorted(df["type_subtype"].unique())

# Define the UI for the dashboard
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_select(
            id="type_subtype",
            label="Select Type and Subtype",
            choices=unique_combinations,
            selected=unique_combinations[0]
        ),
        title="Filter Controls",
    ),
    ui.layout_column_wrap(
        ui.output_text("alert_count"),
        ui.output_text("common_location"),
        fill=False,
    ),
    ui.layout_columns(
        ui.card(
            ui.card_header("Alert Locations (Scatterplot)"),
            output_widget("alert_scatter"),
            full_screen=True,
        ),
        ui.card(
            ui.card_header("Top 10 Locations Summary"),
            ui.output_data_frame("location_summary"),
            full_screen=True,
        ),
    ),
    title="Waze Alerts Dashboard",
    fillable=True,
)

# Define the server logic
def server(input, output, session):
    @reactive.calc
    def filtered_df():
        # Filter data based on the selected type-subtype
        selected = input.type_subtype()
        return df[df["type_subtype"] == selected]

    @reactive.calc
    def top_locations():
        # Group by latitude and longitude, count occurrences, and get the top 10 dynamically
        return (
            filtered_df()
            .sort_values(by="count", ascending=False)
            .head(10)
            [[
                "type_subtype",  # Include the type_subtype column
                "binned_latitude",
                "binned_longitude",
                "count"
            ]]
        )

    @render.text
    def alert_count():
        # Total number of alerts for the selected type-subtype
        total_alerts = filtered_df()["count"].sum()
        return f"{input.type_subtype()}: {total_alerts} alerts in total (including non-top 10 bins)"

    @render.text
    def common_location():
        # Most common location for the selected type-subtype
        if not top_locations().empty:
            top = top_locations().iloc[0]
            return f"Location with highest count: {top['binned_latitude']}, {top['binned_longitude']} ({top['count']} alerts)"
        return "No data"

    @render_altair
    def alert_scatter():
        # Extract min and max latitude and longitude from GeoJSON for plotting
        flat_coords = []
        for feature in chicago_geojson["features"]:
            geometry = feature["geometry"]
            if geometry["type"] == "Polygon":
                for ring in geometry["coordinates"]:
                    flat_coords.extend(ring)
            elif geometry["type"] == "MultiPolygon":
                for polygon in geometry["coordinates"]:
                    for ring in polygon:
                        flat_coords.extend(ring)

        # Get min/max longitude and latitude from Chicago GeoJSON
        min_long_chi = min(coord[0] for coord in flat_coords)
        max_long_chi = max(coord[0] for coord in flat_coords)
        min_lat_chi = min(coord[1] for coord in flat_coords)
        max_lat_chi = max(coord[1] for coord in flat_coords)

        # Get top locations for the selected type-subtype
        top_locs = top_locations()

        # Prepare the scatter plot
        scatter_plot = alt.Chart(top_locs).mark_point().encode(
            alt.X("binned_longitude:Q", scale=alt.Scale(
                domain=[min_long_chi, max_long_chi]), title="Longitude"),
            alt.Y("binned_latitude:Q", scale=alt.Scale(
                domain=[min_lat_chi, max_lat_chi]), title="Latitude"),
            size="count",
            tooltip=["binned_latitude", "binned_longitude", "count"]
        ).project(type="identity").properties(
            height=400,
            width=400
        )

        # Prepare the background map
        background = alt.Chart(geo_data).mark_geoshape(
            fill="lightgray",
            stroke="white"
        ).project(type="identity", reflectY=True).properties(
            width=400,
            height=400
        )

        # Combine the background and scatter plot
        return background + scatter_plot

    @render.data_frame
    def location_summary():
        # Return the top 10 locations as a DataFrame
        return top_locations()

app = App(app_ui, server)