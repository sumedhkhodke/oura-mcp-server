import { defineRailway, github, project, service, volume } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "oura-mcp-server";
export default defineRailway(() => {
  // Holds the rotating Oura token file (OURA_TOKEN_FILE) and FastMCP's OAuth
  // state (FASTMCP_HOME). Must stay declared and mounted: dropping it from this
  // file makes `railway config apply` detach it.
  const data = volume("oura-mcp-server-volume", {
    sizeMB: 5000,
    region: "us-west2",
    allowOnlineResize: true,
  });

  const ouraMcpServer = service("oura-mcp-server", {
    source: github("sumedhkhodke/oura-mcp-server", { branch: "main", checkSuites: true }),
    // No start command: the Dockerfile CMD owns startup, and a Railway start
    // command runs without a shell, so $PORT would not expand.
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    replicas: { "us-west2": 1 },
    // restartPolicyType defaults to ON_FAILURE; Railway reports the default as null, so
    // declaring it would show as a permanent plan diff.
    deploy: { restartPolicyMaxRetries: 3 },
    volumeMounts: { "/data": data },
  });

  return project("oura-mcp-server", {
    // Variables (secrets included) stay in Railway, never in this file.
    variables: { managed: false },
    resources: [data, ouraMcpServer],
  });
});
