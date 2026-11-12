package com.websitebrief.backend.service;

import com.websitebrief.backend.exception.AiServiceUnavailableException;
import java.util.List;
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
    private final String baseUrl;

    public AiServiceClient(RestTemplate restTemplate,
                           @Value("${ai.service.base-url:http://127.0.0.1:8000}") String baseUrl) {
        this.restTemplate = restTemplate;
        this.baseUrl = baseUrl.replaceAll("/+$", "");
    }

    /**
     * 把 JSON 请求体转发给 Python AI 服务，响应（包括状态码和错误体）原样带回。
     * 用 byte[] 接收，避免 Spring 在缺少 charset 时按 ISO-8859-1 解码导致中文乱码。
     */
    public ResponseEntity<byte[]> postJson(String path, Object body) {
        String url = baseUrl + path;

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        HttpEntity<Object> request = new HttpEntity<>(body, headers);

        try {
            ResponseEntity<byte[]> response =
                    restTemplate.exchange(url, HttpMethod.POST, request, byte[].class);
            return ResponseEntity.status(response.getStatusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(response.getBody());
        } catch (HttpStatusCodeException e) {
            // FastAPI 的业务错误（如 400/502 + detail），原样透传给前端
            log.warn("AI service {} returned {}: {}", path, e.getStatusCode(), e.getStatusText());
            return ResponseEntity.status(e.getStatusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(e.getResponseBodyAsByteArray());
        } catch (ResourceAccessException e) {
            log.error("cannot reach AI service at {}", url, e);
            throw new AiServiceUnavailableException(
                    "无法连接 AI 服务（" + url + "），请确认 ai-service 已在 8000 端口启动。", e);
        }
    }
}
