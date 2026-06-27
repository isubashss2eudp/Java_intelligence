package com.demo.controller;

import com.demo.service.OrderService;
import com.demo.service.AuthService;
import java.util.List;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @Autowired
    private OrderService orderService;

    @Autowired
    private AuthService authService;

    public List<String> getOrders(String userId) {
        authService.validateUser(userId);
        return orderService.getOrdersForUser(userId);
    }
}
