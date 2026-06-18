// static/swagger_init.js
// Bootstraps Swagger UI pointing to the static OpenAPI specification

document.addEventListener("DOMContentLoaded", function() {
    window.ui = SwaggerUIBundle({
        url: "/static/openapi.json",
        dom_id: '#swagger-ui',
        presets: [
            SwaggerUIBundle.presets.apis,
            SwaggerUIBundle.presets.SwaggerUIStandalonePreset
        ],
        layout: "BaseLayout",
        deepLinking: true
    });
});
