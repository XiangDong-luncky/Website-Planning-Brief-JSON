package com.websitebrief.backend.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record GenerateRequest(
        @NotBlank(message = "idea 不能为空")
        @Size(max = 2000, message = "idea 长度不能超过 2000 字")
        String idea) {
}
