#!/usr/bin/env python3
"""
Example script demonstrating DRL Scheduler usage
"""

import requests
import json
import time
from typing import Dict, Any

# Configuration
SCHEDULER_API = "http://localhost:8000"


def get_scheduler_status() -> Dict[str, Any]:
    """Get current scheduler status"""
    response = requests.get(f"{SCHEDULER_API}/status")
    return response.json()


def get_cluster_state() -> Dict[str, Any]:
    """Get current cluster state"""
    response = requests.get(f"{SCHEDULER_API}/cluster/state")
    return response.json()


def get_node_metrics() -> Dict[str, Any]:
    """Get metrics for all nodes"""
    response = requests.get(f"{SCHEDULER_API}/cluster/nodes")
    return response.json()


def trigger_training(episodes: int = 1, save_model: bool = True) -> Dict[str, Any]:
    """Manually trigger training"""
    response = requests.post(
        f"{SCHEDULER_API}/training/trigger",
        json={"episodes": episodes, "save_model": save_model}
    )
    return response.json()


def save_model() -> Dict[str, Any]:
    """Save the current model"""
    response = requests.post(f"{SCHEDULER_API}/model/save")
    return response.json()


def get_config() -> Dict[str, Any]:
    """Get current configuration"""
    response = requests.get(f"{SCHEDULER_API}/config")
    return response.json()


def monitor_scheduling(duration: int = 60):
    """Monitor scheduling decisions for a duration"""
    print(f"Monitoring scheduler for {duration} seconds...\n")

    start_time = time.time()
    initial_status = get_scheduler_status()

    while time.time() - start_time < duration:
        time.sleep(5)

        status = get_scheduler_status()
        cluster = get_cluster_state()

        print(f"\r[{time.time() - start_time:.0f}s] "
              f"Scheduled: {status['scheduled_pods']}, "
              f"Failed: {status['failed_schedules']}, "
              f"Episodes: {status['training_episodes']}, "
              f"Epsilon: {status['epsilon']:.3f}, "
              f"CPU: {cluster['cluster_cpu_usage']:.2%}, "
              f"Memory: {cluster['cluster_memory_usage']:.2%}",
              end='')

    print("\n\nFinal Status:")
    print(json.dumps(status, indent=2))


def print_node_distribution():
    """Print pod distribution across nodes"""
    nodes = get_node_metrics()

    print("\nNode Distribution:")
    print("-" * 80)
    print(f"{'Node Name':<30} {'CPU Usage':<12} {'Memory Usage':<15} {'Pods':<8}")
    print("-" * 80)

    for node_name, metrics in sorted(nodes.items()):
        print(f"{node_name:<30} "
              f"{metrics['cpu_usage']:<12.2%} "
              f"{metrics['memory_usage']:<15.2%} "
              f"{metrics['pod_count']:<8}")

    print("-" * 80)


def main():
    """Main function"""
    print("=" * 80)
    print("DRL Kubernetes Scheduler - Example Usage")
    print("=" * 80)

    try:
        # 1. Get initial status
        print("\n1. Getting scheduler status...")
        status = get_scheduler_status()
        print(json.dumps(status, indent=2))

        # 2. Get configuration
        print("\n2. Getting configuration...")
        config = get_config()
        print(json.dumps(config, indent=2))

        # 3. Get cluster state
        print("\n3. Getting cluster state...")
        cluster = get_cluster_state()
        print(json.dumps(cluster, indent=2))

        # 4. Print node distribution
        print("\n4. Node distribution:")
        print_node_distribution()

        # 5. Monitor scheduling (optional)
        print("\n5. Monitoring scheduling decisions...")
        print("Press Ctrl+C to skip...")
        try:
            monitor_scheduling(duration=30)
        except KeyboardInterrupt:
            print("\nSkipped monitoring")

        # 6. Trigger training (optional)
        print("\n6. Triggering manual training...")
        response = input("Trigger training? (y/N): ")
        if response.lower() == 'y':
            result = trigger_training(episodes=5)
            print(json.dumps(result, indent=2))

        # 7. Save model
        print("\n7. Saving model...")
        response = input("Save model? (y/N): ")
        if response.lower() == 'y':
            result = save_model()
            print(json.dumps(result, indent=2))

        print("\n" + "=" * 80)
        print("Example completed successfully!")
        print("=" * 80)

    except requests.exceptions.ConnectionError:
        print(f"\nError: Cannot connect to scheduler API at {SCHEDULER_API}")
        print("Make sure the scheduler is running and accessible.")
        print("\nTo port-forward:")
        print("  kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8000:8000")
    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    main()
