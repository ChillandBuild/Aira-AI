-- TeleCMI CHUB India click-to-call uses a per-agent login token (agentLogin),
-- minted from agent id + password. Store the password alongside the existing
-- telecmi_agent_id so each telecaller's own mobile rings on agentConnect.
alter table callers add column if not exists telecmi_agent_password text;
