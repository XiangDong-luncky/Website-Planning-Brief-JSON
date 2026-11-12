package com.websitebrief.backend.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.websitebrief.backend.exception.InvalidRequestException;
import com.websitebrief.backend.service.AiServiceClient;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "*")
public class GenerateController {

    private final AiServiceClient aiServiceClient;

    public GenerateController(AiServiceClient aiServiceClient) {
        this.aiServiceClient = aiServiceClient;
    }

    @PostMapping(value = "/chat", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<byte[]> chat(@RequestBody JsonNode body) {
        requireMessages(body);
        return aiServiceClient.postJson("/chat", body);
    }

    @PostMapping(value = "/generate-outline", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<byte[]> generateOutline(@RequestBody JsonNode body) {
        requireMessages(body);
        return aiServiceClient.postJson("/generate-outline", body);
    }

    @PostMapping(value = "/generate-page-html", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<byte[]> generatePageHtml(@RequestBody JsonNode body) {
        JsonNode page = body.path("page");
        if (!page.isObject() || page.path("name").asText("").isBlank()) {
            throw new InvalidRequestException("page 不能为空，且必须包含 name 字段");
        }
        return aiServiceClient.postJson("/generate-page-html", body);
    }

    private void requireMessages(JsonNode body) {
        JsonNode messages = body.path("messages");
        if (!messages.isArray() || messages.isEmpty()) {
            throw new InvalidRequestException("messages 不能为空，且必须是数组");
        }
    }
}
