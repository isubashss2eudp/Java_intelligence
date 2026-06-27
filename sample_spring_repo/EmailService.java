package com.demo.service;

import com.demo.config.EmailConfig;

@Service
public class EmailService {

    @Autowired
    private EmailConfig emailConfig;

    public void sendOrderConfirmation(String orderId) {}
}
