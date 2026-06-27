package com.demo.service;

import com.demo.repository.CustomerRepository;

@Service
public class CustomerService {

    @Autowired
    private CustomerRepository customerRepo;

    public String getCustomer(String id) {
        return customerRepo.findById(id);
    }
}
