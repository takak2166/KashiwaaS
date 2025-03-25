"""
Visualization Module
Provides functionality for visualizing Slack message data
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

# Set matplotlib backend to Agg (non-interactive) before importing pyplot
import matplotlib
matplotlib.use('Agg')  # This must be done before importing pyplot

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


def create_hourly_distribution_chart(
    hourly_data: Dict[int, int],
    title: str = "Hourly Message Distribution",
    figsize: Tuple[int, int] = (10, 6)
) -> Figure:
    """
    Create hourly distribution chart
    
    Args:
        hourly_data: Hourly distribution data (hour -> count)
        title: Chart title
        figsize: Figure size
        
    Returns:
        Figure: Matplotlib figure
    """
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Prepare data
    hours = list(range(24))
    counts = [hourly_data.get(hour, 0) for hour in hours]
    
    # Create bar chart
    bars = ax.bar(hours, counts, color='#007bff', alpha=0.7)
    
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
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Number of Messages')
    ax.set_title(title)
    
    # Set x-axis ticks
    ax.set_xticks(hours)
    ax.set_xticklabels([f'{h:02d}:00' for h in hours], rotation=45)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)
    
    # Add grid
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Tight layout
    fig.tight_layout()
    
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
    fig: Figure,
    filename: str,
    dpi: int = 100,
    format: str = 'png'
) -> str:
    """
    Save figure to file
    
    Args:
        fig: Matplotlib figure
        filename: Output filename (without extension)
        dpi: DPI for output
        format: Output format (png, jpg, svg, pdf)
        
    Returns:
        str: Path to saved file
    """
    output_path = f"{filename}.{format}"
    fig.savefig(output_path, dpi=dpi, format=format, bbox_inches='tight')
    plt.close(fig)
    
    logger.info(f"Saved figure to {output_path}")
    return output_path


def create_daily_report_charts(
    stats: Dict[str, Any],
    output_dir: str = "reports"
) -> Dict[str, str]:
    """
    Create charts for daily report
    
    Args:
        stats: Daily statistics
        output_dir: Output directory
        
    Returns:
        Dict[str, str]: Chart paths
    """
    # Create hourly distribution chart
    hourly_fig = create_hourly_distribution_chart(
        stats['hourly_distribution'],
        title=f"Hourly Message Distribution ({stats['date']})"
    )
    hourly_path = save_figure(hourly_fig, f"{output_dir}/hourly_{stats['date']}")
    
    # Create reaction chart if there are reactions
    reaction_path = None
    if stats['top_reactions']:
        reaction_fig = create_reaction_chart(
            stats['top_reactions'],
            title=f"Top Reactions ({stats['date']})"
        )
        reaction_path = save_figure(reaction_fig, f"{output_dir}/reactions_{stats['date']}")
    
    # Create user activity chart if there are users
    user_path = None
    if stats['user_stats']:
        user_fig = create_user_activity_chart(
            stats['user_stats'],
            title=f"Top Active Users ({stats['date']})"
        )
        user_path = save_figure(user_fig, f"{output_dir}/users_{stats['date']}")
    
    return {
        "hourly": hourly_path,
        "reactions": reaction_path,
        "users": user_path
    }


def create_weekly_report_charts(
    daily_stats: List[Dict[str, Any]],
    output_dir: str = "reports"
) -> Dict[str, str]:
    """
    Create charts for weekly report
    
    Args:
        daily_stats: List of daily statistics
        output_dir: Output directory
        
    Returns:
        Dict[str, str]: Chart paths
    """
    # Prepare data for daily activity chart
    daily_data = {stats['date']: stats['message_count'] for stats in daily_stats}
    
    # Create daily activity chart
    start_date = min(daily_stats, key=lambda x: x['date'])['date']
    end_date = max(daily_stats, key=lambda x: x['date'])['date']
    daily_fig = create_daily_activity_chart(
        daily_data,
        title=f"Daily Message Activity ({start_date} to {end_date})"
    )
    daily_path = save_figure(daily_fig, f"{output_dir}/daily_{start_date}_to_{end_date}")
    
    # Aggregate reaction data
    reaction_counts = {}
    for stats in daily_stats:
        for reaction in stats['top_reactions']:
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
    
    # Create reaction chart if there are reactions
    reaction_path = None
    if top_reactions:
        reaction_fig = create_reaction_chart(
            top_reactions,
            title=f"Top Reactions ({start_date} to {end_date})"
        )
        reaction_path = save_figure(reaction_fig, f"{output_dir}/reactions_{start_date}_to_{end_date}")
    
    # Aggregate user data
    user_counts = {}
    for stats in daily_stats:
        for user in stats['user_stats']:
            username = user['username']
            count = user['message_count']
            if username in user_counts:
                user_counts[username] += count
            else:
                user_counts[username] = count
    
    # Sort users by count
    top_users = [
        {"username": username, "message_count": count}
        for username, count in sorted(user_counts.items(), key=lambda x: x[1], reverse=True)
    ][:10]  # Top 10
    
    # Create user activity chart if there are users
    user_path = None
    if top_users:
        user_fig = create_user_activity_chart(
            top_users,
            title=f"Top Active Users ({start_date} to {end_date})"
        )
        user_path = save_figure(user_fig, f"{output_dir}/users_{start_date}_to_{end_date}")
    
    return {
        "daily": daily_path,
        "reactions": reaction_path,
        "users": user_path
    }