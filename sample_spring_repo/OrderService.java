package com.demo.service;

import com.demo.repository.OrderRepository;
import com.demo.repository.CustomerRepository;
import com.demo.service.EmailService;
import java.util.List;

@Service
public class OrderService {

    private final OrderRepository orderRepo;
    private final CustomerRepository customerRepo;
    private final EmailService emailService;

    public OrderService(
            OrderRepository orderRepo,
            CustomerRepository customerRepo,
            EmailService emailService) {
        this.orderRepo = orderRepo;
        this.customerRepo = customerRepo;
        this.emailService = emailService;
    }

    public List<String> getOrdersForUser(String userId) {
        return orderRepo.findByUserId(userId);
    }
}
