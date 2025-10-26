#!/usr/bin/env python3
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
Main entry point for DRL-Enhanced Kubernetes Scheduler
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from scheduler.k8s_scheduler import DRLScheduler
from scheduler.config import SchedulerConfig
from api.server import start_api_server
from monitoring.metrics import setup_metrics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/scheduler.log')
    ]
)

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages the lifecycle of the DRL scheduler"""

    def __init__(self):
        self.scheduler: Optional[DRLScheduler] = None
        self.config = SchedulerConfig()
        self.running = False

    async def start(self):
        """Start the scheduler and all components"""
        logger.info("Starting DRL-Enhanced Kubernetes Scheduler")

        try:
            # Setup metrics collection
            setup_metrics()
            logger.info("Metrics collection initialized")

            # Initialize the scheduler
            self.scheduler = DRLScheduler(self.config)
            await self.scheduler.initialize()
            logger.info("DRL Scheduler initialized")

            # Start API server in background
            api_task = asyncio.create_task(
                start_api_server(self.scheduler, self.config)
            )
            logger.info(f"API server starting on port {self.config.api_port}")

            # Start the scheduling loop
            self.running = True
            schedule_task = asyncio.create_task(self.scheduler.run())

            logger.info("DRL Scheduler is now running")

            # Wait for both tasks
            await asyncio.gather(api_task, schedule_task)

        except Exception as e:
            logger.error(f"Error starting scheduler: {e}", exc_info=True)
            raise

    async def stop(self):
        """Gracefully stop the scheduler"""
        logger.info("Stopping DRL Scheduler...")
        self.running = False

        if self.scheduler:
            await self.scheduler.shutdown()

        logger.info("DRL Scheduler stopped")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    sys.exit(0)


async def main():
    """Main function"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    manager = SchedulerManager()

    try:
        await manager.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
