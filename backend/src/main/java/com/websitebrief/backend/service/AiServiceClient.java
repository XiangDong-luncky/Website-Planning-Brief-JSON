package com.websitebrief.backend.service;

import com.websitebrief.backend.exception.AiServiceUnavailableException;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

@Service
public class AiServiceClient {

    private static final Logger log = LoggerFactory.getLogger(AiServiceClient.class);

    private final RestTemplate restTemplate;
    private final String generateUrl;

    public AiServiceClient(RestTemplate restTemplate,
                           @Value("${ai.service.base-url:http://127.0.0.1:8000}") String baseUrl) {
        this.restTemplate = restTemplate;
        this.generateUrl = baseUrl.replaceAll("/+$", "") + "/generate";
    }

    /**
     * 调用 Python AI 服务，把响应（包括状态码和错误体）原样带回。
     * 用 byte[] 接收，避免 Spring 在缺少 charset 时按 ISO-8859-1 解码导致中文乱码。
     */
    public ResponseEntity<byte[]> generate(String idea) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(java.util.List.of(MediaType.APPLICATION_JSON));

        HttpEntity<Map<String, String>> request = new HttpEntity<>(Map.of("idea", idea), headers);

        try {
            ResponseEntity<byte[]> response =
                    restTemplate.exchange(generateUrl, HttpMethod.POST, request, byte[].class);
            return ResponseEntity.status(response.getStatusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(response.getBody());
        } catch (HttpStatusCodeException e) {
            // FastAPI 的业务错误（如 502 + detail），原样透传给前端
            log.warn("AI service returned {}: {}", e.getStatusCode(), e.getStatusText());
            return ResponseEntity.status(e.getStatusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(e.getResponseBodyAsByteArray());
        } catch (ResourceAccessException e) {
            log.error("cannot reach AI service at {}", generateUrl, e);
            throw new AiServiceUnavailableException(
                    "无法连接 AI 服务（" + generateUrl + "），请确认 ai-service 已在 8000 端口启动。", e);
        }
    }
}
