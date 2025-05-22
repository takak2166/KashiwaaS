"""
Visualization Module
Provides functionality for visualizing Slack message data
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union

# Set matplotlib backend to Agg (non-interactive) before importing pyplot
import matplotlib
matplotlib.use('Agg')  # This must be done before importing pyplot

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure
import numpy as np
import plotly.graph_objects as go

from src.utils.logger import get_logger

logger = get_logger(__name__)


def create_reaction_pie_chart(
    reaction_data: List[Dict[str, Any]],
    title: str = "Reaction Distribution",
    figsize: Tuple[int, int] = (10, 10)
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
    counts = [item['count'] for item in reaction_data]
    
    # Create pie chart
    wedges, texts, autotexts = ax.pie(
        counts,
        autopct='%1.1f%%',
        textprops={'color': "w"},
        shadow=True,
        startangle=90
    )
    
    # Equal aspect ratio ensures that pie is drawn as a circle
    ax.axis('equal')
    
    # Add legend
    ax.legend(
        wedges,
        [f"{name} ({count})" for name, count in zip(names, counts)],
        title="Reactions",
        loc="center left",
        bbox_to_anchor=(1, 0, 0.5, 1)
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
    group_by: int = 1  # 1 for hourly, 2 for every 2 hours, etc.
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
    
    # Prepare data
    if group_by > 1:
        # Group hours
        grouped_data = {}
        for hour in range(0, 24, group_by):
            group_count = sum(hourly_data.get(h, 0) for h in range(hour, min(hour + group_by, 24)))
            grouped_data[hour] = group_count
        
        hours = list(range(0, 24, group_by))
        counts = [grouped_data.get(hour, 0) for hour in hours]
        labels = [f'{h:02d}:00-{(h+group_by)%24:02d}:00' for h in hours]
    else:
        # Use hourly data as is
        hours = list(range(24))
        counts = [hourly_data.get(hour, 0) for hour in hours]
        labels = [f'{h:02d}:00' for h in hours]
    
    # Create bar chart
    bars = ax.bar(range(len(hours)), counts, color='#007bff', alpha=0.7)
    
    # Add value labels on top of bars
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2.,
                height + 0.1,
                f'{int(height)}',
                ha='center',
                va='bottom',
                fontsize=9
            )
    
    # Set labels and title
    ax.set_xlabel('Time of Day')
    ax.set_ylabel('Number of Messages')
    ax.set_title(title)
    
    # Set x-axis ticks
    ax.set_xticks(range(len(hours)))
    ax.set_xticklabels(labels, rotation=45)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)
    
    # Add grid
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Tight layout
    fig.tight_layout()
    
    return fig


def create_hourly_line_chart(
    hourly_data: Dict[int, int],
    title: str = "Hourly Message Distribution",
    figsize: Tuple[int, int] = (10, 6),
    group_by: int = 1  # 1 for hourly, 2 for every 2 hours, etc.
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
    
    # Prepare data
    if group_by > 1:
        # Group hours
        grouped_data = {}
        for hour in range(0, 24, group_by):
            group_count = sum(hourly_data.get(h, 0) for h in range(hour, min(hour + group_by, 24)))
            grouped_data[hour] = group_count
        
        hours = list(range(0, 24, group_by))
        counts = [grouped_data.get(hour, 0) for hour in hours]
        labels = [f'{h:02d}:00-{(h+group_by)%24:02d}:00' for h in hours]
    else:
        # Use hourly data as is
        hours = list(range(24))
        counts = [hourly_data.get(hour, 0) for hour in hours]
        labels = [f'{h:02d}:00' for h in hours]
    
    # Create line chart
    x_values = range(len(hours))
    ax.plot(x_values, counts, marker='o', linestyle='-', color='#007bff', markersize=8)
    
    # Add value labels above points
    for i, count in enumerate(counts):
        if count > 0:
            ax.text(
                i,
                count + max(counts) * 0.02,
                f'{int(count)}',
                ha='center',
                va='bottom',
                fontsize=9
            )
    
    # Set labels and title
    ax.set_xlabel('Time of Day')
    ax.set_ylabel('Number of Messages')
    ax.set_title(title)
    
    # Set x-axis ticks
    ax.set_xticks(x_values)
    ax.set_xticklabels(labels, rotation=45)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)
    
    # Add grid
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Tight layout
    fig.tight_layout()
    
    return fig


def create_weekly_hourly_line_chart(
    stats: Dict[str, Any],
    title: str = "Message Activity Over Week"
) -> go.Figure:
    """
    Create a line chart showing message activity by hour over a week
    
    Args:
        stats: Weekly statistics
        title: Chart title
        
    Returns:
        go.Figure: Plotly figure
    """
    # Get hourly message counts
    hourly_counts = stats['hourly_message_counts']
    
    # Get date range
    start_date = datetime.strptime(stats['start_date'], '%Y-%m-%d')
    
    # Aggregate counts into 2-hour intervals
    two_hour_counts = []
    two_hour_labels = []
    for day in range(7):
        current_date = start_date + timedelta(days=day)
        for hour in range(0, 24, 2):
            # Sum counts for current 2-hour interval
            count = sum(hourly_counts[day*24 + hour:day*24 + hour + 2])
            two_hour_counts.append(count)
            # Format label as yyyy-mm-dd hh:mm
            label = f"{current_date.strftime('%Y-%m-%d')} {hour:02d}:00"
            two_hour_labels.append(label)
    
    # Create figure
    fig = go.Figure()
    
    # Add single line for the entire week
    fig.add_trace(go.Scatter(
        x=two_hour_labels,
        y=two_hour_counts,
        mode='lines+markers',
        name="Message Count"
    ))
    
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
            tickmode='array',
            tickvals=two_hour_labels[::3],  # Show tick marks every 3 hours
            ticktext=two_hour_labels[::3],  # Display date and time
            showticklabels=True  # Show tick labels
        )
    )
    
    return fig


def create_daily_activity_chart(
    daily_data: Dict[str, int],
    title: str = "Daily Message Activity",
    figsize: Tuple[int, int] = (10, 6)
) -> Figure:
    """
    Create daily activity chart
    
    Args:
        daily_data: Daily activity data (date string -> count)
        title: Chart title
        figsize: Figure size
        
    Returns:
        Figure: Matplotlib figure
    """
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Prepare data
    dates = [datetime.strptime(date_str, "%Y-%m-%d") for date_str in daily_data.keys()]
    counts = list(daily_data.values())
    
    # Create line chart
    ax.plot(dates, counts, marker='o', linestyle='-', color='#007bff', markersize=8)
    
    # Add value labels
    for i, count in enumerate(counts):
        ax.text(
            dates[i],
            count + max(counts) * 0.02,
            f'{count}',
            ha='center',
            va='bottom',
            fontsize=9
        )
    
    # Set labels and title
    ax.set_xlabel('Date')
    ax.set_ylabel('Number of Messages')
    ax.set_title(title)
    
    # Format x-axis as dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    plt.xticks(rotation=45)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)
    
    # Add grid
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Tight layout
    fig.tight_layout()
    
    return fig


def create_reaction_chart(
    reaction_data: List[Dict[str, Any]],
    title: str = "Top Reactions",
    figsize: Tuple[int, int] = (10, 6)
) -> Figure:
    """
    Create reaction chart
    
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
    names = [item['name'] for item in reaction_data]
    counts = [item['count'] for item in reaction_data]
    
    # Create horizontal bar chart
    bars = ax.barh(names, counts, color='#007bff', alpha=0.7)
    
    # Add value labels
    for bar in bars:
        width = bar.get_width()
        ax.text(
            width + max(counts) * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f'{int(width)}',
            ha='left',
            va='center',
            fontsize=9
        )
    
    # Set labels and title
    ax.set_xlabel('Count')
    ax.set_ylabel('Reaction')
    ax.set_title(title)
    
    # Set y-axis to show reaction names
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([f':{name}:' for name in names])
    
    # Set x-axis to start at 0
    ax.set_xlim(left=0)
    
    # Add grid
    ax.grid(axis='x', linestyle='--', alpha=0.7)
    
    # Tight layout
    fig.tight_layout()
    
    return fig


def create_user_activity_chart(
    user_data: List[Dict[str, Any]],
    title: str = "Top Active Users",
    figsize: Tuple[int, int] = (10, 6)
) -> Figure:
    """
    Create user activity chart
    
    Args:
        user_data: User data (list of dicts with 'username' and 'message_count')
        title: Chart title
        figsize: Figure size
        
    Returns:
        Figure: Matplotlib figure
    """
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Prepare data
    usernames = [item['username'] for item in user_data]
    counts = [item['message_count'] for item in user_data]
    
    # Create horizontal bar chart
    bars = ax.barh(usernames, counts, color='#007bff', alpha=0.7)
    
    # Add value labels
    for bar in bars:
        width = bar.get_width()
        ax.text(
            width + max(counts) * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f'{int(width)}',
            ha='left',
            va='center',
            fontsize=9
        )
    
    # Set labels and title
    ax.set_xlabel('Number of Messages')
    ax.set_ylabel('User')
    ax.set_title(title)
    
    # Set x-axis to start at 0
    ax.set_xlim(left=0)
    
    # Add grid
    ax.grid(axis='x', linestyle='--', alpha=0.7)
    
    # Tight layout
    fig.tight_layout()
    
    return fig


def save_figure(
    fig: Union[Figure, go.Figure],
    filename: str,
    dpi: int = 100,
    format: str = 'png'
) -> str:
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
        fig.savefig(output_path, dpi=dpi, format=format, bbox_inches='tight')
        plt.close(fig)
        logger.info(f"Saved Matplotlib figure to {output_path}")
    
    return output_path

def create_weekly_report_charts(
    stats: Dict[str, Any],
    output_dir: str = "reports"
) -> Dict[str, str]:
    """
    Create charts for weekly report
    
    Args:
        stats: Weekly statistics
        output_dir: Output directory
        
    Returns:
        Dict[str, str]: Chart paths
    """
    # Get date range
    start_date = stats['start_date']
    end_date = stats['end_date']
    
    # Create weekly hourly line chart (168 hours)
    weekly_hourly_fig = create_weekly_hourly_line_chart(
        stats,
        title=f"Message Activity Over Week ({start_date} to {end_date})"
    )
    weekly_hourly_path = save_figure(weekly_hourly_fig, f"{output_dir}/hourly_weekly")
    
    # Create reaction pie chart if there are reactions
    reaction_pie_path = None
    if stats['reaction_count'] > 0:
        # Aggregate reaction data
        reaction_counts = {}
        for post in stats['top_posts']:
            for reaction in post['reactions']:
                name = reaction['name']
                count = reaction['count']
                if name in reaction_counts:
                    reaction_counts[name] += count
                else:
                    reaction_counts[name] = count
        
        # Sort reactions by count
        top_reactions = [
            {"name": name, "count": count}
            for name, count in sorted(reaction_counts.items(), key=lambda x: x[1], reverse=True)
        ][:10]  # Top 10
        
        # Pie chart for reactions
        reaction_pie_fig = create_reaction_pie_chart(
            top_reactions,
            title=f"Reaction Distribution ({start_date} to {end_date})"
        )
        reaction_pie_path = save_figure(reaction_pie_fig, f"{output_dir}/reaction_pie_weekly")
    
    return {
        "hourly": weekly_hourly_path,
        "reaction_pie": reaction_pie_path
    }