package handlers

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestMCPManagementMutationsHonorServerReadonly(t *testing.T) {
	t.Parallel()
	handler := &MCPHandler{readonlyMode: true}
	tests := []struct {
		name    string
		method  string
		path    string
		handler http.HandlerFunc
	}{
		{name: "create", method: http.MethodPost, path: "/api/mcp/servers", handler: handler.CreateServerHandler()},
		{name: "update", method: http.MethodPut, path: "/api/mcp/servers/server-1", handler: handler.UpdateServerHandler()},
		{name: "delete", method: http.MethodDelete, path: "/api/mcp/servers/server-1", handler: handler.DeleteServerHandler()},
		{name: "connect", method: http.MethodPost, path: "/api/mcp/servers/server-1/connect", handler: handler.ConnectServerHandler()},
		{name: "disconnect", method: http.MethodPost, path: "/api/mcp/servers/server-1/disconnect", handler: handler.DisconnectServerHandler()},
		{name: "test", method: http.MethodPost, path: "/api/mcp/servers/server-1/test", handler: handler.TestConnectionHandler()},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			test.handler.ServeHTTP(recorder, httptest.NewRequest(test.method, test.path, nil))
			if recorder.Code != http.StatusForbidden {
				t.Fatalf("status=%d want=%d body=%s", recorder.Code, http.StatusForbidden, recorder.Body.String())
			}
		})
	}
}
