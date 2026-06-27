package com.demo.repository;

import java.util.List;

@Repository
public interface OrderRepository {
    List<String> findByUserId(String userId);
}
