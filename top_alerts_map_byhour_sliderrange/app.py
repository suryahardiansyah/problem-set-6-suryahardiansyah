import pandas as pd
import altair as alt
import json
from pathlib import Path
from shiny import App, reactive, render, ui, Inputs
from shinywidgets import render_altair, output_widget

# Define the path to the CSV and GeoJSON files and load the data
df = pd.read_csv("top_alerts_map_byhour/top_alerts_map_byhour.csv")
geojson_file = "top_alerts_map_byhour/chicago-boundaries.geojson"

# Load the GeoJSON file
with open(geojson_file) as f:
    chicago_geojson = json.load(f)

# Prepare Altair GeoJSON data
geo_data = alt.Data(values=chicago_geojson["features"])

# Prepare unique type-subtype combinations for the dropdown
df["type_subtype"] = df["updated_type"] + " - " + df["updated_subtype"]
unique_combinations = sorted(df["type_subtype"].unique())

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_select(
            id="type_subtype",
            label="Select Type and Subtype",
            choices=unique_combinations,
            selected=unique_combinations[0],
        ),
        ui.input_switch(
            id="toggle_range",
            label="Toggle to switch to range of hours",
            value=False,
        ),
        ui.output_ui("hour_input"),
        title="Filter Controls",
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
    title="Waze Alerts by Hour Range Dashboard",
    fillable=True,
)

# Define the server logic
def server(input, output, session):
    @output
    @render.ui
    def hour_input():
        # Dynamically show single-hour or range-of-hours slider based on toggle
        if input.toggle_range():
            return ui.input_slider(
                id="hour_range",
                label="Select Hour Range",
                min=0,
                max=23,
                value=[6, 9],
                step=1,
                ticks=True,
            )
        else:
            return ui.input_slider(
                id="hour",
                label="Select Hour",
                min=0,
                max=23,
                value=12,
                step=1,
                ticks=True,
            )

    @reactive.calc
    def filtered_df():
        selected = input.type_subtype()
        if input.toggle_range():
            # Filter by range of hours
            start_hour, end_hour = input.hour_range()
            return df[
                (df["type_subtype"] == selected)
                & (df["hour"].str[:2].astype(int).between(start_hour, end_hour))
            ]
        else:
            # Filter by single hour
            selected_hour = f"{input.hour():02}:00"
            return df[(df["type_subtype"] == selected) & (df["hour"] == selected_hour)]

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
                "count",
            ]]
        )

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

        # Get top locations for the selected type-subtype and time range
        top_locs = top_locations()

        # Prepare the scatter plot
        scatter_plot = alt.Chart(top_locs).mark_point().encode(
            alt.X(
                "binned_longitude:Q",
                scale=alt.Scale(domain=[min_long_chi, max_long_chi]),
                title="Longitude",
            ),
            alt.Y(
                "binned_latitude:Q",
                scale=alt.Scale(domain=[min_lat_chi, max_lat_chi]),
                title="Latitude",
            ),
            size="count",
            tooltip=["binned_latitude", "binned_longitude", "count"],
        ).properties(
            height=400,
            width=400,
            title=(
                f"{input.type_subtype()} Alerts"
                + (f" from {input.hour_range()[0]}:00 to {input.hour_range()[1]}:00"
                   if input.toggle_range()
                   else f" at {input.hour():02}:00")
            ),
        )

        # Prepare the background map
        background = alt.Chart(geo_data).mark_geoshape(
            fill="lightgray",
            stroke="white",
        ).project(type="identity", reflectY=True).properties(
            width=400,
            height=400,
        )

        # Combine the background and scatter plot
        return background + scatter_plot

    @render.data_frame
    def location_summary():
        # Return the top 10 locations as a DataFrame
        return top_locations()


app = App(app_ui, server)