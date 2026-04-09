# Using TigerGraph-MCP with GitHub Copilot Chat

## 1. Install TigerGraph-MCP

```bash
pip install tigergraph-mcp
```

## 2. Create the `.env` File

In the root of your project, create a `.env` file:

```bash
TG_HOST=http://127.0.0.1
TG_USERNAME=tigergraph
TG_PASSWORD=tigergraph
```

You can also use API token authentication:

```bash
TG_HOST=http://127.0.0.1
TG_API_TOKEN=your_api_token_here
```

See the main [README](../README.md) for all configuration options.

## 3. Enable Agent Mode in Copilot Chat

Open GitHub Copilot Chat and switch to **Agent** mode using the Mode dropdown.

## 4. Create `.vscode/mcp.json`

Add the following configuration to `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "tigergraph-mcp-server": {
      "command": "tigergraph-mcp",
      "args": ["-vv"],
      "envFile": "${workspaceFolder}/.env"
    }
  }
}
```

Click the **Start** button that appears above `"tigergraph-mcp-server":` to start the server.

## 5. View Available Tools

Click the Tools icon in the Chat view to see all TigerGraph-MCP tools. There are 50+ tools covering schema, data, queries, vectors, and more.

---

## Workflow Examples

Below are example prompts you can paste into Copilot Chat. Each walks through a common TigerGraph workflow step by step.

### Example 1: Create a Graph from CSV Samples

Paste the following into Copilot Chat:

```
I have the following CSV data. Please create a TigerGraph graph schema for it:

person.csv:
id,name,age,gender
p1,Alice,30,Female
p2,Bob,32,Male
p3,Charlie,28,Male

company.csv:
id,name,industry
c1,TigerGraph,Technology
c2,Acme,Manufacturing

knows.csv:
from_id,to_id,since
p1,p2,2020-01-01
p2,p3,2021-06-15

works_for.csv:
person_id,company_id,role
p1,c1,Engineer
p2,c1,Manager
p3,c2,Analyst
```

Copilot will use the `tigergraph__create_graph` tool to create the schema. You can review and modify the parameters before confirming.

After the graph is created, you can follow up with:

```
Load the data from these local files into the graph:
- /home/tigergraph/data/person.csv
- /home/tigergraph/data/company.csv
- /home/tigergraph/data/knows.csv
- /home/tigergraph/data/works_for.csv
```

Then check the results:

```
How many vertices and edges are in the graph?
```

### Example 2: Load Data from S3

```
Create an S3 data source named "s3_anonymous_source" with anonymous access
(provider: org.apache.hadoop.fs.s3a.AnonymousAWSCredentialsProvider)
```

```
Preview the file s3a://tigergraph-solution-kits/connected_customer/customer_360/data/Individual_Info.csv
from the s3_anonymous_source data source
```

```
Also preview s3a://tigergraph-solution-kits/connected_customer/customer_360/data/Account_Info.csv
```

```
Based on the previewed data, create a graph schema called Customer360Graph
with appropriate vertex and edge types
```

```
Create a loading job and load both files into the graph
```

```
How many vertices and edges are in Customer360Graph?
```

### Example 3: Query and Explore

```
Show me the schema of Customer360Graph
```

```
How many Individual vertices are there?
```

```
Get the first 5 Individual vertices
```

```
Drop the graph Customer360Graph
```

---

## Tips

- **Step by step**: For complex workflows, break your instructions into individual steps. This gives you a chance to review each tool call before proceeding.
- **Review parameters**: Click "See more" on any tool call to inspect and edit the parameters before running.
- **Destructive actions**: Copilot will ask for confirmation before dropping graphs or data sources.
- **Discover tools**: Ask Copilot "What TigerGraph tools are available?" and it will use the `tigergraph__discover_tools` tool to list them.
- **Workflow templates**: Ask "Show me the workflow for data loading" and Copilot will use `tigergraph__get_workflow` to show step-by-step instructions.
