# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
FastAPI server for DRL scheduler management and monitoring
"""

import logging
import asyncio
import threading
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from scheduler.config import SchedulerConfig
from monitoring.metrics import REGISTRY

logger = logging.getLogger(__name__)


# Global scheduler reference (set by start_api_server)
_scheduler = None


app = FastAPI(
    title="DRL Kubernetes Scheduler API",
    description="API for managing and monitoring the DRL-enhanced scheduler",
    version="1.0.0"
)


class SchedulerStatus(BaseModel):
    """Scheduler status response"""
    status: str
    scheduled_pods: int
    failed_schedules: int
    training_episodes: int
    epsilon: float
    model_version: str


class TrainingRequest(BaseModel):
    """Request to trigger training"""
    episodes: int = 1
    save_model: bool = True


# Global scheduler reference (set by start_api_server)
_scheduler = None


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "DRL Kubernetes Scheduler",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if _scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    return {"status": "healthy"}


@app.get("/readiness")
async def readiness_check():
    """Readiness check endpoint"""
    if _scheduler is None or not hasattr(_scheduler, 'drl_agent'):
        raise HTTPException(status_code=503, detail="Scheduler not ready")

    return {"status": "ready"}


@app.get("/status", response_model=SchedulerStatus)
async def get_status():
    """Get scheduler status"""
    if _scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    return SchedulerStatus(
        status="running",
        scheduled_pods=_scheduler.scheduled_pods,
        failed_schedules=_scheduler.failed_schedules,
        training_episodes=_scheduler.training_episodes,
        epsilon=_scheduler.drl_agent.epsilon if _scheduler.drl_agent else 0.0,
        model_version="1.0.0"
    )


@app.get("/cluster/state")
async def get_cluster_state():
    """Get current cluster state"""
    if _scheduler is None or not _scheduler.state_observer:
        raise HTTPException(status_code=503, detail="State observer not initialized")

    state = await _scheduler.state_observer.get_state()

    return JSONResponse(content={
        "cluster_cpu_usage": state.get('cluster_cpu_usage', 0),
        "cluster_memory_usage": state.get('cluster_memory_usage', 0),
        "total_nodes": state.get('total_nodes', 0),
        "ready_nodes": state.get('ready_nodes', 0),
        "total_pods": state.get('total_pods', 0),
        "load_balance_score": state.get('load_balance_score', 0),
        "timestamp": str(state.get('timestamp', ''))
    })


@app.get("/cluster/nodes")
async def get_node_metrics():
    """Get metrics for all nodes"""
    if _scheduler is None or not _scheduler.state_observer:
        raise HTTPException(status_code=503, detail="State observer not initialized")

    state = await _scheduler.state_observer.get_state()

    return JSONResponse(content=state.get('nodes', {}))


@app.get("/cluster/nodes/{node_name}")
async def get_node_detail(node_name: str):
    """Get detailed metrics for a specific node"""
    if _scheduler is None or not _scheduler.state_observer:
        raise HTTPException(status_code=503, detail="State observer not initialized")

    metrics = await _scheduler.state_observer.get_node_metrics(node_name)

    if not metrics:
        raise HTTPException(status_code=404, detail=f"Node {node_name} not found")

    return JSONResponse(content=metrics)


@app.post("/training/trigger")
async def trigger_training(request: TrainingRequest):
    """Manually trigger training"""
    if _scheduler is None or not _scheduler.drl_agent:
        raise HTTPException(status_code=503, detail="DRL agent not initialized")

    try:
        results = []
        for _ in range(request.episodes):
            metrics = await _scheduler.drl_agent.train()
            results.append(metrics)

        if request.save_model:
            await _scheduler.drl_agent.save_model()

        return {
            "status": "success",
            "episodes_completed": request.episodes,
            "results": results
        }
    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/model/save")
async def save_model():
    """Save the current model"""
    if _scheduler is None or not _scheduler.drl_agent:
        raise HTTPException(status_code=503, detail="DRL agent not initialized")

    try:
        await _scheduler.drl_agent.save_model()
        return {"status": "success", "message": "Model saved"}
    except Exception as e:
        logger.error(f"Failed to save model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/model/load")
async def load_model():
    """Load a saved model"""
    if _scheduler is None or not _scheduler.drl_agent:
        raise HTTPException(status_code=503, detail="DRL agent not initialized")

    try:
        await _scheduler.drl_agent.load_model()
        return {"status": "success", "message": "Model loaded"}
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config")
async def get_config():
    """Get current scheduler configuration"""
    if _scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    return {
        "scheduler_name": _scheduler.config.scheduler_name,
        "enable_training": _scheduler.config.enable_training,
        "training_interval": _scheduler.config.training_interval,
        "learning_rate": _scheduler.config.learning_rate,
        "gamma": _scheduler.config.gamma,
        "epsilon": _scheduler.drl_agent.epsilon if _scheduler.drl_agent else 0.0,
        "reward_weights": _scheduler.config.reward_weights
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(REGISTRY)


async def start_api_server(scheduler, config: SchedulerConfig):
    """Start the FastAPI server in a background thread"""
    global _scheduler
    _scheduler = scheduler

    logger.info(f"Starting API server on port {config.api_port}")
    logger.info(f"Scheduler reference set: {_scheduler is not None}")

    # Run uvicorn in a separate thread to avoid async issues
    def run_server():
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=config.api_port,
            log_level="info",
            access_log=False
        )

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    logger.info("===== UVICORN SERVER STARTED IN BACKGROUND THREAD =====")

    # Keep the task alive
    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("API server task cancelled")
        raise