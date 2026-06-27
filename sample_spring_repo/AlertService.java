package com.demo.service;

import com.demo.service.NotificationService;

@Service
public class AlertService {

    @Autowired
    private NotificationService notificationService;

    public void sendAlert(String msg) {
        notificationService.notify(msg);
    }
}
