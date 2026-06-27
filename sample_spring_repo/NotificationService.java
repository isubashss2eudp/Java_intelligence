package com.demo.service;

import com.demo.service.AlertService;

@Service
public class NotificationService {

    @Autowired
    private AlertService alertService;

    public void notify(String msg) {
        alertService.sendAlert(msg);
    }
}
