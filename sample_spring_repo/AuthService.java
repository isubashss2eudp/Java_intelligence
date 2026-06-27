package com.demo.service;

import com.demo.repository.UserRepository;

@Service
public class AuthService {

    @Autowired
    private UserRepository userRepo;

    public void validateUser(String userId) {
        userRepo.findById(userId);
    }
}
