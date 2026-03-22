"""
Provides visualization functionality for analysis results.
"""

from datetime import datetime
from typing import Any, Dict, List, Tuple, Union

import matplotlib

matplotlib.use("Agg")  # Set the backend to Agg before importing pyplot
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from matplotlib.figure import Figure

from src.analysis.types import WeeklyStats
from src.analysis.visualization_prep import (
    aggregate_reaction_totals_from_top_posts,
    build_weekly_two_hour_series,
    group_hourly_dict,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def create_reaction_pie_chart(
    reaction_data: List[Dict[str, Any]],
    title: str = "Reaction Distribution",
    figsize: Tuple[int, int] = (5, 5),
) -> Figure:
    """
    Create a pie chart of reaction distribution

    Args:
        reaction_data: Reaction data (list of dicts with 'name' and 'count')
        title: Chart title
        figsize: Figure size

    Returns:
        Figure: Matplotlib figure
    """
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)

    # Prepare data
    names = [f":{item['name']}:" for item in reaction_data]
    counts = [item["count"] for item in reaction_data]

    # Create pie chart
    wedges, texts, autotexts = ax.pie(counts, autopct="%1.1f%%", textprops={"color": "w"}, shadow=True, startangle=90)

    # Equal aspect ratio ensures that pie is drawn as a circle
    ax.axis("equal")

    # Add legend
    ax.legend(
        wedges,
        [f"{name} ({count})" for name, count in zip(names, counts)],
        title="Reactions",
        loc="center left",
        bbox_to_anchor=(1, 0, 0.5, 1),
    )

    # Set title
    ax.set_title(title)

    # Tight layout
    fig.tight_layout()

    return fig


def create_hourly_distribution_chart(
    hourly_data: Dict[int, int],
    title: str = "Hourly Message Distribution",
    figsize: Tuple[int, int] = (10, 6),
    group_by: int = 1,  # 1 for hourly, 2 for every 2 hours, etc.
) -> Figure:
    """
    Create hourly distribution chart as bar chart

    Args:
        hourly_data: Hourly distribution data (hour -> count)
        title: Chart title
        figsize: Figure size
        group_by: Group hours by this number (1 for hourly, 2 for every 2 hours, etc.)

    Returns:
        Figure: Matplotlib figure
    """
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)

    counts, hours, labels = group_hourly_dict(hourly_data, group_by)

    # Create bar chart
    bars = ax.bar(range(len(hours)), counts, color="#007bff", alpha=0.7)

    # Add value labels on top of bars
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + 0.1,
                f"{int(height)}",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    # Set labels and title
    ax.set_xlabel("Time of Day")
    ax.set_ylabel("Number of Messages")
    ax.set_title(title)

    # Set x-axis ticks
    ax.set_xticks(range(len(hours)))
    ax.set_xticklabels(labels, rotation=45)

    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)

    # Add grid
    ax.grid(axis="y", linestyle="--", alpha=0.7)

    # Tight layout
    fig.tight_layout()

    return fig


def create_hourly_line_chart(
    hourly_data: Dict[int, int],
    title: str = "Hourly Message Distribution",
    figsize: Tuple[int, int] = (10, 6),
    group_by: int = 1,  # 1 for hourly, 2 for every 2 hours, etc.
) -> Figure:
    """
    Create hourly distribution chart as line chart

    Args:
        hourly_data: Hourly distribution data (hour -> count)
        title: Chart title
        figsize: Figure size
        group_by: Group hours by this number (1 for hourly, 2 for every 2 hours, etc.)

    Returns:
        Figure: Matplotlib figure
    """
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)

    counts, hours, labels = group_hourly_dict(hourly_data, group_by)

    # Create line chart
    x_values = range(len(hours))
    ax.plot(x_values, counts, marker="o", linestyle="-", color="#007bff", markersize=8)

    # Add value labels above points
    for i, count in enumerate(counts):
        if count > 0:
            ax.text(
                i,
                count + max(counts) * 0.02,
                f"{int(count)}",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    # Set labels and title
    ax.set_xlabel("Time of Day")
    ax.set_ylabel("Number of Messages")
    ax.set_title(title)

    # Set x-axis ticks
    ax.set_xticks(x_values)
    ax.set_xticklabels(labels, rotation=45)

    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)

    # Add grid
    ax.grid(axis="y", linestyle="--", alpha=0.7)

    # Tight layout
    fig.tight_layout()

    return fig


def create_weekly_hourly_line_chart(stats: WeeklyStats, title: str = "Message Activity Over Week") -> go.Figure:
    """
    Create a line chart showing message activity by hour over a week

    Args:
        stats: Weekly statistics
        title: Chart title

    Returns:
        go.Figure: Plotly figure
    """
    hourly_counts = list(stats.hourly_message_counts)
    start_date = datetime.strptime(stats.start_date, "%Y-%m-%d")
    two_hour_counts, two_hour_labels = build_weekly_two_hour_series(start_date, hourly_counts)

    # Create figure
    fig = go.Figure()

    # Add single line for the entire week
    fig.add_trace(
        go.Scatter(
            x=two_hour_labels,
            y=two_hour_counts,
            mode="lines+markers",
            name="Message Count",
        )
    )

    # Update layout
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Message Count",
        showlegend=True,
        template="plotly_white",
        width=1600,  # Set width to 1600px
        height=800,  # Adjust height accordingly
        xaxis=dict(
            tickangle=-45,  # Display at 45 degrees upward
            tickmode="array",
            tickvals=two_hour_labels[::3],  # Show tick marks every 3 hours
            ticktext=two_hour_labels[::3],  # Display date and time
            showticklabels=True,  # Show tick labels
        ),
    )

    return fig


def save_figure(fig: Union[Figure, go.Figure], filename: str, dpi: int = 100, format: str = "png") -> str:
    """
    Save figure to file

    Args:
        fig: Matplotlib or Plotly figure
        filename: Output filename (without extension)
        dpi: DPI for output (only used for Matplotlib)
        format: Output format (png, jpg, svg, pdf)

    Returns:
        str: Path to saved file
    """
    output_path = f"{filename}.{format}"

    if isinstance(fig, go.Figure):
        fig.write_image(output_path)
        logger.info(f"Saved Plotly figure to {output_path}")
    else:
        fig.savefig(output_path, dpi=dpi, format=format, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"Saved Matplotlib figure to {output_path}")

    return output_path


def create_weekly_report_charts(stats: WeeklyStats, output_dir: str = "reports") -> Dict[str, str]:
    """
    Create charts for weekly report

    Args:
        stats: Weekly statistics
        output_dir: Output directory

    Returns:
        Dict[str, str]: Chart paths
    """
    start_date = stats.start_date
    end_date = stats.end_date

    weekly_hourly_fig = create_weekly_hourly_line_chart(
        stats, title=f"Message Activity Over Week ({start_date} to {end_date})"
    )
    weekly_hourly_path = save_figure(weekly_hourly_fig, f"{output_dir}/hourly_weekly")

    reaction_pie_path = None
    if stats.reaction_count > 0:
        top_reactions = aggregate_reaction_totals_from_top_posts(list(stats.top_posts), limit=10)

        # Pie chart for reactions
        reaction_pie_fig = create_reaction_pie_chart(
            top_reactions, title=f"Reaction Distribution ({start_date} to {end_date})"
        )
        reaction_pie_path = save_figure(reaction_pie_fig, f"{output_dir}/reaction_pie_weekly")

    return {"hourly": weekly_hourly_path, "reaction_pie": reaction_pie_path}
