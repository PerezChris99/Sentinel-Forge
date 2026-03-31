# Windows Database Setup (No Docker)

Since you have chosen not to use Docker, you must install the database services manually on your Windows machine.

## Prerequisites
1.  **PostgreSQL 15 or 16**
2.  **pgvector** extension
3.  **Redis**

## Step 1: Install PostgreSQL
1.  Download the installer from [EnterpriseDB](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads).
2.  Run the installer.
    *   **Password**: Set the password to `sentinelforge` (or update your `.env` file later).
    *   **Port**: Keep default `5432`.
3.  Open **Stack Builder** (it asks to launch after installation).
    *   Select your PostgreSQL installation.
    *   (Optional) You can try to find extensions here, but `pgvector` usually needs manual install on Windows.

## Step 2: Install pgvector
1.  Go to the [pgvector Release Page](https://github.com/pgvector/pgvector/releases).
2.  Download the zip file for Windows (e.g., `pgvector_0.5.1_win64.zip`).
3.  Extract the files.
4.  Copy the contents of `lib` to `C:\Program Files\PostgreSQL\15\lib`.
5.  Copy the contents of `share\extension` to `C:\Program Files\PostgreSQL\15\share\extension`.
6.  Open **pgAdmin** or a SQL shell (psql) and run:
    ```sql
    CREATE EXTENSION vector;
    ```

## Step 3: Install Redis
1.  Redis does not officially support Windows, but you can use a port.
2.  Download the installer from [Memurai](https://www.memurai.com/get-memurai) (Redis-compatible for Windows) OR use [WSL](https://learn.microsoft.com/en-us/windows/wsl/install).
3.  Ensure the Redis service is running on port `6379`.

## Step 4: Create Database
1.  Open `psql` or pgAdmin.
2.  Run:
    ```sql
    CREATE DATABASE sentinelforge;
    CREATE USER sentinelforge WITH PASSWORD 'sentinelforge';
    GRANT ALL PRIVILEGES ON DATABASE sentinelforge TO sentinelforge;
    \c sentinelforge
    CREATE EXTENSION vector;
    ```

## Step 5: Run Migrations
Once the database is running locally:
1.  Double-click `setup_db.bat` in the `sentinelforge` folder.
