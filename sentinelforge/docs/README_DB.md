# Database Setup Guide

SentinelForge requires PostgreSQL with **TimescaleDB** and **pgvector** extensions, as well as **Redis**.

## Option 1: Docker (Recommended)

1.  Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2.  Open a terminal in the `sentinelforge` directory.
3.  Run the following command to start the database and Redis:
    ```bash
    docker-compose up -d --build
    ```
4.  Once the containers are running, apply the database migrations:
    ```bash
    ..\env\Scripts\alembic upgrade head
    ```

## Option 2: Manual Installation

1.  Install PostgreSQL 15+.
2.  Install [TimescaleDB](https://docs.timescale.com/self-hosted/latest/install/).
3.  Install [pgvector](https://github.com/pgvector/pgvector).
4.  Install [Redis](https://redis.io/docs/getting-started/installation/).
5.  Create a database named `sentinelforge`.
6.  Update the `.env` file with your database credentials.
7.  Run migrations:
    ```bash
    ..\env\Scripts\alembic upgrade head
    ```
