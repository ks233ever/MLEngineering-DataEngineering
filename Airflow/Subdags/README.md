Commonly repeated series of tasks in DAGs can be captured as reusable SubDAGs

**dag.py** 
  * Runs two subdags in parallel
    * The subdag contains a PostgresOperator to create a table, a S3ToRedshiftOperator to load data to the tables, and a custom HasRowsOperator to verify data was inserted
    * See **subdag.py**
  * Performs a calculation
  
  
**DAG Tree**

  ![alt text](images/dt.png?raw=true)

**DAG Graph**

  ![alt text](images/dg.png?raw=true)
