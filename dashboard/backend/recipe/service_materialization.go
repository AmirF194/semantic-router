package recipe

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

func materializeChatRequest(probe ProbeDetail) (ChatRequest, error) {
	messages := cloneObjects(probe.Messages)
	if len(messages) == 0 {
		text, err := materializeText(probe)
		if err != nil {
			return ChatRequest{}, err
		}
		messages = []map[string]any{{"role": "user", "content": text}}
	}
	request := ChatRequest{
		Model:    probe.Model,
		Messages: messages,
		Tools:    cloneObjects(probe.Tools),
	}
	data, err := json.Marshal(request)
	if err != nil {
		return ChatRequest{}, fmt.Errorf("%w: encode run plan: %w", ErrInvalid, err)
	}
	if len(data) > maxRequestBytes {
		return ChatRequest{}, fmt.Errorf("%w: materialized request exceeds %d byte limit", ErrBadRequest, maxRequestBytes)
	}
	return request, nil
}

func materializeEvalRequest(probe ProbeDetail) (EvalRequest, error) {
	request := EvalRequest{
		Model: probe.Model,
		Tools: cloneObjects(probe.Tools),
	}
	if len(probe.Messages) > 0 {
		request.Messages = cloneObjects(probe.Messages)
	} else {
		text, err := materializeText(probe)
		if err != nil {
			return EvalRequest{}, err
		}
		request.Text = text
	}
	data, err := json.Marshal(request)
	if err != nil {
		return EvalRequest{}, fmt.Errorf("%w: encode eval request: %w", ErrInvalid, err)
	}
	if len(data) > maxRequestBytes {
		return EvalRequest{}, fmt.Errorf("%w: materialized request exceeds %d byte limit", ErrBadRequest, maxRequestBytes)
	}
	return request, nil
}

func materializeText(probe ProbeDetail) (string, error) {
	if probe.Query == "" {
		return "", fmt.Errorf("%w: text probe has no query", ErrInvalid)
	}
	repeated, err := repeatLinesBounded(probe.Query, probe.Repeat, maxRequestBytes)
	if err != nil {
		return "", err
	}
	if probe.Padding == nil {
		return repeated, nil
	}
	extraSeparators := 1
	if probe.Padding.Placement == "around" && probe.Padding.Repeat > 1 {
		extraSeparators = 2
	}
	padding, err := repeatLinesBounded(probe.Padding.Text, probe.Padding.Repeat, maxRequestBytes-len(repeated)-extraSeparators)
	if err != nil {
		return "", err
	}
	text, err := placeProbePadding(probe, repeated, padding)
	if err != nil {
		return "", err
	}
	if len(text) > maxRequestBytes {
		return "", fmt.Errorf("%w: materialized query exceeds %d byte limit", ErrBadRequest, maxRequestBytes)
	}
	return text, nil
}

func placeProbePadding(probe ProbeDetail, repeated, padding string) (string, error) {
	switch probe.Padding.Placement {
	case "before":
		return joinNonEmpty(padding, repeated), nil
	case "after":
		return joinNonEmpty(repeated, padding), nil
	case "around":
		return placeAroundProbePadding(probe, repeated)
	default:
		return "", fmt.Errorf("%w: unsupported padding placement %q", ErrInvalid, probe.Padding.Placement)
	}
}

func placeAroundProbePadding(probe ProbeDetail, repeated string) (string, error) {
	midpoint := probe.Padding.Repeat / 2
	before := ""
	if midpoint > 0 {
		var err error
		before, err = repeatLinesBounded(probe.Padding.Text, midpoint, maxRequestBytes)
		if err != nil {
			return "", err
		}
	}
	after, err := repeatLinesBounded(probe.Padding.Text, probe.Padding.Repeat-midpoint, maxRequestBytes)
	if err != nil {
		return "", err
	}
	return joinNonEmpty(before, repeated, after), nil
}

func repeatLinesBounded(value string, repeat, limit int) (string, error) {
	if repeat < 1 || limit < 0 {
		return "", fmt.Errorf("%w: materialized query exceeds %d byte limit", ErrBadRequest, maxRequestBytes)
	}
	lineBytes := len(value)
	separators := repeat - 1
	if separators > limit || lineBytes > (limit-separators)/repeat {
		return "", fmt.Errorf("%w: materialized query exceeds %d byte limit", ErrBadRequest, maxRequestBytes)
	}
	total := lineBytes*repeat + separators
	if total > limit {
		return "", fmt.Errorf("%w: materialized query exceeds %d byte limit", ErrBadRequest, maxRequestBytes)
	}
	return strings.TrimSuffix(strings.Repeat(value+"\n", repeat), "\n"), nil
}

func joinNonEmpty(parts ...string) string {
	nonEmpty := parts[:0]
	for _, part := range parts {
		if part != "" {
			nonEmpty = append(nonEmpty, part)
		}
	}
	return strings.Join(nonEmpty, "\n")
}

func cloneObjects(items []map[string]any) []map[string]any {
	if len(items) == 0 {
		return nil
	}
	cloned := make([]map[string]any, len(items))
	for i, item := range items {
		cloned[i] = make(map[string]any, len(item))
		for key, value := range item {
			cloned[i][key] = cloneJSONValue(value)
		}
	}
	return cloned
}

func contains(values []string, value string) bool {
	for _, candidate := range values {
		if candidate == value {
			return true
		}
	}
	return false
}

func stableUnique(values []string) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0, len(values))
	for _, value := range values {
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func probeKey(decisionID, variantID string) string {
	return decisionID + "\x00" + variantID
}

func decodeStrictYAML(data []byte, target any) error {
	decoder := yaml.NewDecoder(bytes.NewReader(data))
	decoder.KnownFields(true)
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("must contain exactly one YAML document")
		}
		return err
	}
	return nil
}

func sortedKeys(values map[string]struct{}) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
