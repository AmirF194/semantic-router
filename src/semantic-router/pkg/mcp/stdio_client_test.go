package mcp

import (
	"strings"
	"testing"
)

func TestEnvironmentVariableLogSummaryOmitsValues(t *testing.T) {
	const sentinelValue = "stdio-env-value-canary"

	summary := environmentVariableLogSummary(map[string]string{
		"SECOND_NAME": "ordinary",
		"FIRST_NAME":  sentinelValue,
	})

	if strings.Contains(summary, sentinelValue) || strings.Contains(summary, "FIRST_NAME=") {
		t.Fatalf("environment summary exposed a configured value: %q", summary)
	}
	if summary != "Environment variable names (2): [FIRST_NAME SECOND_NAME]" {
		t.Fatalf("environment summary = %q", summary)
	}
}
